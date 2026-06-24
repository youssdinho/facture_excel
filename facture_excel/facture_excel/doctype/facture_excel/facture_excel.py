import base64
import io
import unicodedata

import frappe
from frappe.model.document import Document


class FactureExcel(Document):
	def validate(self):
		self._calculate_total()
		self._validate_unique_active()

	def before_submit(self):
		self._validate_total_match()

	def on_submit(self):
		_refresh_fac_com(self.sales_invoice)

	def on_cancel(self):
		_refresh_fac_com(self.sales_invoice)

	def _sync_autoname_field(self):
		"""Override Frappe's sync pour préserver sales_invoice = SI original.
		Sans cet override, Frappe écrase sales_invoice avec le nom du document
		(ex: 'X-1' au lieu de 'X') lors d'un amend, cassant la liaison.
		"""
		pass

	def _calculate_total(self):
		total = sum((row.amount or 0) for row in self.items)
		self.total_commercial = total

	def _validate_total_match(self):
		if not self.grand_total:
			frappe.throw("Impossible de valider : la Facture ERPNext liée n'a pas de total.")

		diff = abs((self.total_commercial or 0) - self.grand_total)
		if diff > 0.000009:
			frappe.throw(
				f"Le total commercial ({frappe.format(self.total_commercial, {'fieldtype': 'Currency'})}) "
				f"doit être égal au total de la Facture ERPNext "
				f"({frappe.format(self.grand_total, {'fieldtype': 'Currency'})})."
			)

	def _validate_unique_active(self):
		"""Une seule Facture Excel active (non annulée) par Sales Invoice."""
		existing = frappe.db.get_value(
			"Facture Excel",
			{
				"sales_invoice": self.sales_invoice,
				"docstatus": ["<", 2],
				"name": ["!=", self.name],
			},
			"name",
		)
		if existing:
			frappe.throw(
				f"Une Facture Excel active existe déjà pour cette facture : "
				f'<a href="/app/facture-excel/{existing}">{existing}</a>',
				title="Doublon détecté",
			)


def _refresh_fac_com(si_name):
	"""Recalcule fac_com en interrogeant l'état réel des Factures Excel liées.
	Gère correctement les cas d'annulation + amend.
	"""
	if not si_name:
		return
	has_submitted = frappe.db.exists(
		"Facture Excel",
		{"sales_invoice": si_name, "docstatus": 1},
	)
	frappe.db.set_value(
		"Sales Invoice", si_name, "fac_com",
		"OUI" if has_submitted else "NON",
		update_modified=False,
	)


@frappe.whitelist()
def import_pdf_bl(files_data):
	"""Parse un ou plusieurs BL PDF et retourne les articles fusionnés.
	files_data : liste JSON de {file_name, file_data (base64)}
	Déduplication par Réf (code article) pendant le traitement.
	"""
	import json
	import pdfplumber

	if isinstance(files_data, str):
		files_data = json.loads(files_data)

	# ref -> {description, qty, weighted_sum (qty*rate), skipped}
	merged = {}
	skipped = []
	total_files = len(files_data)

	for file_obj in files_data:
		file_name = file_obj.get("file_name", "")
		if not file_name.lower().endswith(".pdf"):
			skipped.append({"file": file_name, "reason": "pas un fichier PDF"})
			continue

		try:
			raw = base64.b64decode(file_obj["file_data"])
		except Exception:
			skipped.append({"file": file_name, "reason": "impossible de décoder le fichier"})
			continue

		try:
			with pdfplumber.open(io.BytesIO(raw)) as pdf:
				for page in pdf.pages:
					tables = page.extract_tables()
					for table in tables:
						_parse_bl_table(table, merged, skipped, file_name)
		except Exception as e:
			skipped.append({"file": file_name, "reason": f"erreur lecture PDF : {e}"})

	# Construire la liste finale
	items = []
	for ref, data in merged.items():
		qty = data["qty"]
		rate = round(data["weighted_sum"] / qty, 5) if qty else 0
		items.append({
			"description": data["description"],
			"qty": qty,
			"rate": rate,
			"amount": round(qty * rate, 5),
		})

	return {
		"items": items,
		"imported": len(items),
		"files": total_files,
		"skipped": skipped,
	}


@frappe.whitelist()
def import_pdf_bl_grouped(files_data):
	"""Parse un ou plusieurs BL PDF en conservant le groupement par BL.

	Contrairement à import_pdf_bl, aucune fusion entre BL : chaque ligne garde
	son numéro de BL et sa date. Les lignes sont retournées dans l'ordre des BL,
	chacune portant bl_no / bl_date pour permettre un affichage groupé.
	files_data : liste JSON de {file_name, file_data (base64)}
	"""
	import json
	import pdfplumber

	if isinstance(files_data, str):
		files_data = json.loads(files_data)

	all_items = []
	skipped = []
	bl_count = 0

	for file_obj in files_data:
		file_name = file_obj.get("file_name", "")
		if not file_name.lower().endswith(".pdf"):
			skipped.append({"file": file_name, "reason": "pas un fichier PDF"})
			continue

		try:
			raw = base64.b64decode(file_obj["file_data"])
		except Exception:
			skipped.append({"file": file_name, "reason": "impossible de décoder le fichier"})
			continue

		try:
			with pdfplumber.open(io.BytesIO(raw)) as pdf:
				full_text = "\n".join((p.extract_text() or "") for p in pdf.pages)
				bl_no, bl_date = _extract_bl_header(full_text, file_name)

				lines = []
				for page in pdf.pages:
					for table in page.extract_tables():
						_parse_bl_table_grouped(table, lines, skipped, file_name)
		except Exception as e:
			skipped.append({"file": file_name, "reason": f"erreur lecture PDF : {e}"})
			continue

		if not lines:
			skipped.append({"file": file_name, "reason": "aucune ligne article détectée"})
			continue

		bl_count += 1
		for ln in lines:
			ln["bl_no"] = bl_no
			ln["bl_date"] = bl_date
			all_items.append(ln)

	return {
		"items": all_items,
		"imported": len(all_items),
		"bls": bl_count,
		"files": len(files_data),
		"skipped": skipped,
	}


def _extract_bl_header(text, file_name):
	"""Extrait (numéro_bl, date) depuis le texte d'un BL OMAG.

	Format attendu : 'LIVRAISON : 2029059633 Le 28/03/2026 13:52'.
	Fallback sur les chiffres du nom de fichier si le motif est absent.
	"""
	import re

	m = re.search(
		r"LIVRAISON\s*:?\s*(\d+)\s+Le\s+(\d{1,2}/\d{1,2}/\d{4})",
		text or "",
		re.IGNORECASE,
	)
	if m:
		return m.group(1).strip(), m.group(2).strip()

	# Fallback : numéro depuis le nom de fichier, date introuvable
	digits = re.search(r"(\d{6,})", file_name or "")
	bl_no = digits.group(1) if digits else (file_name or "BL")
	return bl_no, ""


def _parse_bl_table_grouped(table, lines, skipped, file_name):
	"""Extrait les lignes articles d'un tableau pdfplumber SANS fusion.

	Le prix unitaire est recalculé à partir du montant ligne (M.TTC), fiable,
	plutôt que de la colonne PU TTC qui est tronquée à l'extraction.
	"""
	if not table or len(table) < 2:
		return

	header = [str(c).strip().lower().replace("\n", " ") if c else "" for c in table[0]]

	idx_ref    = _find_col(header, {"réf", "ref", "référence", "code"})
	idx_desc   = _find_col(header, {"description", "désignation", "libellé", "article"})
	idx_qty    = _find_col(header, {"qté", "qty", "quantité", "qte"})
	idx_amount = _find_col(header, {"m.ttc", "mttc", "m ttc", "montant ttc", "montant", "total ttc"})
	idx_pu     = _find_col(header, {"pu ttc", "pu", "prix unitaire", "prix unit.", "p.u ttc"})

	if any(i is None for i in [idx_desc, idx_qty]) or (idx_amount is None and idx_pu is None):
		skipped.append({"file": file_name, "reason": f"colonnes introuvables : {header}"})
		return

	max_idx = max(i for i in [idx_ref, idx_desc, idx_qty, idx_amount, idx_pu] if i is not None)

	for row in table[1:]:
		if not row or len(row) <= max_idx:
			continue

		desc = str(row[idx_desc] or "").strip().replace("\n", " ")
		qty_raw = str(row[idx_qty] or "").strip()

		# Ignorer lignes vides ou totaux
		if not desc or desc.lower() in ("description", "désignation", "total"):
			continue

		try:
			qty = float(qty_raw.replace(" ", "").replace(",", "."))
		except ValueError:
			skipped.append({"file": file_name, "reason": f"ligne '{desc}' : quantité non numérique"})
			continue

		if qty <= 0:
			continue

		# Montant ligne fiable → prix unitaire = montant / qté
		amount = None
		if idx_amount is not None:
			try:
				amount = float(str(row[idx_amount] or "").strip().replace(" ", "").replace(",", "."))
			except ValueError:
				amount = None

		if amount is not None and amount > 0:
			rate = round(amount / qty, 5)
		else:
			# Fallback sur la colonne PU TTC (tronquée mais mieux que rien)
			try:
				rate = float(str(row[idx_pu] or "").strip().replace(" ", "").replace(",", "."))
			except (ValueError, TypeError):
				skipped.append({"file": file_name, "reason": f"ligne '{desc}' : montant et prix illisibles"})
				continue
			amount = round(qty * rate, 5)

		lines.append({
			"description": desc,
			"qty": qty,
			"rate": rate,
			"amount": round(amount, 5),
		})


def _parse_bl_table(table, merged, skipped, file_name):
	"""Extrait les lignes articles d'un tableau pdfplumber et les fusionne dans merged."""
	if not table or len(table) < 2:
		return

	# Détecter les indices de colonnes depuis l'en-tête
	header = [str(c).strip().lower().replace("\n", " ") if c else "" for c in table[0]]

	idx_ref  = _find_col(header, {"réf", "ref", "référence", "code"})
	idx_desc = _find_col(header, {"description", "désignation", "libellé", "article"})
	idx_qty  = _find_col(header, {"qté", "qty", "quantité", "qte"})
	idx_pu   = _find_col(header, {"pu\nttc", "pu ttc", "pu", "prix unitaire", "prix unit.", "p.u ttc"})

	if any(i is None for i in [idx_ref, idx_desc, idx_qty, idx_pu]):
		skipped.append({"file": file_name, "reason": f"colonnes introuvables : {header}"})
		return

	for row in table[1:]:
		if not row or len(row) <= max(idx_ref, idx_desc, idx_qty, idx_pu):
			continue

		ref  = str(row[idx_ref] or "").strip()
		desc = str(row[idx_desc] or "").strip().replace("\n", " ")
		qty_raw = str(row[idx_qty] or "").strip()
		pu_raw  = str(row[idx_pu]  or "").strip()

		# Ignorer lignes vides ou totaux
		if ref.lower() in ("réf", "ref", "total"):
			continue
		if not desc:
			continue

		# Si ref non numérique ou vide → utiliser la description comme clé (ex: article sans code dans le PDF)
		if not ref or not any(c.isdigit() for c in ref):
			merge_key = f"__desc__{desc}"
		else:
			merge_key = ref

		try:
			qty = float(qty_raw.replace(" ", "").replace(",", "."))
			pu  = float(pu_raw.replace(" ", "").replace(",", "."))
		except ValueError:
			skipped.append({"file": file_name, "reason": f"ligne '{desc}' : quantité ou prix non numérique"})
			continue

		if qty <= 0 or pu < 0:
			continue

		if merge_key in merged:
			# Fusion : somme qty + prix pondéré
			merged[merge_key]["weighted_sum"] += qty * pu
			merged[merge_key]["qty"] += qty
		else:
			merged[merge_key] = {
				"description": desc,
				"qty": qty,
				"weighted_sum": qty * pu,
			}


def _find_col(header, aliases):
	"""Retourne l'index de la première colonne dont le nom est dans aliases."""
	for i, h in enumerate(header):
		if h in aliases:
			return i
	return None


def _normalize(text):
	"""Lowercase + strip accents for flexible column matching."""
	if not text:
		return ""
	nfkd = unicodedata.normalize("NFKD", str(text))
	return "".join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()


_COL_MAPS = {
	"description": {"designation", "description", "article", "libelle", "produit", "intitule"},
	"qty":         {"quantite", "qte", "qty", "nombre", "nbre", "q"},
	"rate":        {"prix", "prix unitaire", "price", "tarif", "pu", "unite", "montant unitaire"},
}


def _detect_columns(headers):
	"""Return dict {field: col_index} for detected columns. Returns None if any missing."""
	result = {}
	for field, aliases in _COL_MAPS.items():
		for idx, h in enumerate(headers):
			if _normalize(h) in aliases:
				result[field] = idx
				break
	missing = [f for f in _COL_MAPS if f not in result]
	return result, missing


@frappe.whitelist()
def import_excel(docname, file_data, file_name):
	"""Parse an xlsx file and return items + import summary.
	Called from client JS; updates doc items on the server side.
	"""
	if not file_name.lower().endswith(".xlsx"):
		frappe.throw("Seuls les fichiers .xlsx sont acceptés.")

	try:
		raw = base64.b64decode(file_data)
	except Exception:
		frappe.throw("Impossible de décoder le fichier.")

	try:
		import openpyxl
		wb = openpyxl.load_workbook(filename=io.BytesIO(raw), read_only=True, data_only=True)
		ws = wb.worksheets[0]
		rows = list(ws.iter_rows(values_only=True))
	except Exception as e:
		frappe.throw(f"Erreur de lecture du fichier Excel : {e}")

	if not rows:
		frappe.throw("Le fichier est vide.")

	col_map, missing = _detect_columns(rows[0])
	if missing:
		labels = {"description": "Désignation", "qty": "Quantité", "rate": "Prix Unitaire"}
		frappe.throw(
			"Colonnes introuvables : " + ", ".join(labels[m] for m in missing) +
			".<br>En-têtes détectés : " + ", ".join(str(h) for h in rows[0] if h is not None)
		)

	items = []
	skipped = []

	for i, row in enumerate(rows[1:], start=2):  # start=2 → ligne réelle dans le fichier
		desc  = row[col_map["description"]] if col_map["description"] < len(row) else None
		qty   = row[col_map["qty"]]         if col_map["qty"]         < len(row) else None
		rate  = row[col_map["rate"]]        if col_map["rate"]        < len(row) else None

		reasons = []
		if not desc or str(desc).strip() == "":
			reasons.append("désignation manquante")
		if qty is None or str(qty).strip() == "":
			reasons.append("quantité manquante")
		if rate is None or str(rate).strip() == "":
			reasons.append("prix manquant")

		if reasons:
			skipped.append({"row": i, "reasons": reasons})
			continue

		try:
			qty_val  = float(str(qty).replace(",", "."))
			rate_val = float(str(rate).replace(",", "."))
		except ValueError:
			skipped.append({"row": i, "reasons": ["quantité ou prix non numérique"]})
			continue

		items.append({
			"description": str(desc).strip(),
			"qty":         qty_val,
			"rate":        rate_val,
			"amount":      round(qty_val * rate_val, 5),
		})

	return {"items": items, "imported": len(items), "skipped": skipped}


@frappe.whitelist()
def download_template():
	"""Return a base64-encoded xlsx template with example row."""
	import openpyxl
	from openpyxl.styles import Font, PatternFill, Alignment

	wb = openpyxl.Workbook()
	ws = wb.active
	ws.title = "Articles"

	headers = ["Désignation", "Quantité", "Prix Unitaire"]
	ws.append(headers)

	# Style header row
	header_fill = PatternFill(start_color="111111", end_color="111111", fill_type="solid")
	header_font = Font(bold=True, color="FFFFFF")
	for col_idx, _ in enumerate(headers, start=1):
		cell = ws.cell(row=1, column=col_idx)
		cell.fill = header_fill
		cell.font = header_font
		cell.alignment = Alignment(horizontal="center")

	# Example row
	ws.append(["Exemple article", 2, 150.00])

	# Column widths
	ws.column_dimensions["A"].width = 40
	ws.column_dimensions["B"].width = 12
	ws.column_dimensions["C"].width = 18

	buf = io.BytesIO()
	wb.save(buf)
	buf.seek(0)
	return base64.b64encode(buf.read()).decode("utf-8")


def on_sales_invoice_cancel(doc, method=None):
	"""Annule automatiquement la Facture Excel liée quand la Sales Invoice est annulée."""
	fe_name = frappe.db.get_value(
		"Facture Excel",
		{"sales_invoice": doc.name, "docstatus": 1},
		"name",
	)
	if not fe_name:
		return

	fe_doc = frappe.get_doc("Facture Excel", fe_name)
	fe_doc.cancel()
	frappe.msgprint(
		f"La Facture Excel <b>{fe_name}</b> a été annulée automatiquement.",
		indicator="orange",
		alert=True,
	)
