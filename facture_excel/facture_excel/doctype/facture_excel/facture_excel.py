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
		if diff > 0.009:
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
			"amount":      round(qty_val * rate_val, 2),
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
