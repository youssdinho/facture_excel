// Facture Excel — client script

frappe.ui.form.on("Facture Excel", {
	setup(frm) {
		frm.set_query("sales_invoice", () => ({
			filters: { docstatus: 1 }
		}));
	},

	refresh(frm) {
		if (frm.doc.sales_invoice) {
			frm.add_custom_button(__("Voir Facture ERPNext"), () => {
				frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice);
			});
		}

		if (frm.doc.docstatus === 0) {
			_update_diff(frm, flt(frm.doc.total_commercial));

			frm.add_custom_button(__("Import Excel"), () => _show_import_dialog(frm));
		}
	},
});

frappe.ui.form.on("Facture Excel Item", {
	qty(frm, cdt, cdn) {
		_calc_amount(frm, cdt, cdn);
	},
	rate(frm, cdt, cdn) {
		_calc_amount(frm, cdt, cdn);
	},
	items_remove(frm) {
		_calc_total(frm);
	},
});

function _calc_amount(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const amount = flt(row.qty) * flt(row.rate);
	frappe.model.set_value(cdt, cdn, "amount", amount);
	_calc_total(frm);
}

function _calc_total(frm) {
	let total = 0;
	(frm.doc.items || []).forEach(row => {
		total += flt(row.amount);
	});
	frm.set_value("total_commercial", total);
	// Mise à jour directe ici — pas via l'event total_commercial
	// pour éviter les appels multiples et l'empilement de messages
	_update_diff(frm, total);
}

function _update_diff(frm, total) {
	if (!frm.doc.grand_total) return;
	const diff = flt(total) - flt(frm.doc.grand_total);

	// Toujours vider d'abord pour éviter l'empilement
	frm.set_intro("");

	if (Math.abs(diff) < 0.01) {
		frm.set_intro(__("Total égal à la facture ERPNext ✓"), "green");
	} else {
		const sign = diff > 0 ? "+" : "";
		frm.set_intro(
			__("Écart avec la facture ERPNext : {0}", [sign + format_currency(diff, frm.doc.currency)]),
			"red"
		);
	}
}

function _show_import_dialog(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Importer des articles"),
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "excel_section",
				options: `<div style="margin-bottom:16px;">
					<b style="font-size:12px;">📄 Depuis un fichier Excel (.xlsx)</b>
					<div style="color:#555;line-height:1.6;margin-top:4px;">
						Les colonnes doivent contenir : <b>Désignation</b>, <b>Quantité</b> et <b>Prix Unitaire</b>.<br>
						<span style="color:#e74c3c;">⚠ L'import Excel remplace tous les articles existants.</span>
					</div>
				</div>`,
			},
			{
				fieldtype: "HTML",
				fieldname: "pdf_section",
				options: `<div style="margin-bottom:8px;border-top:1px solid #eee;padding-top:14px;">
					<b style="font-size:12px;">📦 Depuis un ou plusieurs Bons de Livraison (PDF)</b>
					<div style="color:#555;line-height:1.6;margin-top:4px;">
						Les articles sont <b>fusionnés</b> avec ceux déjà présents.<br>
						Les doublons sont détectés par code article : quantités sommées, prix pondéré calculé.
					</div>
				</div>`,
			},
		],
		primary_action_label: __("Importer Excel"),
		primary_action() {
			d.hide();
			_pick_and_import(frm);
		},
		secondary_action_label: __("Importer BL PDF"),
		secondary_action() {
			d.hide();
			_pick_and_import_pdf(frm);
		},
	});
	// Ajouter bouton modèle manuellement
	d.$wrapper.find(".modal-footer").prepend(
		`<button class="btn btn-default btn-sm" id="btn-dl-modele" style="margin-right:auto;">
			Télécharger le modèle Excel
		</button>`
	);
	d.$wrapper.find("#btn-dl-modele").on("click", () => _download_template());
	d.show();
}

function _pick_and_import(frm) {
	const input = document.createElement("input");
	input.type = "file";
	input.accept = ".xlsx";
	input.onchange = function () {
		const file = input.files[0];
		if (!file) return;
		if (!file.name.toLowerCase().endsWith(".xlsx")) {
			frappe.msgprint({ message: __("Seuls les fichiers .xlsx sont acceptés."), indicator: "red" });
			return;
		}
		const reader = new FileReader();
		reader.onload = function (e) {
			const b64 = e.target.result.split(",")[1];
			frappe.call({
				method: "facture_excel.facture_excel.doctype.facture_excel.facture_excel.import_excel",
				args: { docname: frm.doc.name, file_data: b64, file_name: file.name },
				freeze: true,
				freeze_message: __("Importation en cours…"),
				callback(r) {
					if (!r.exc && r.message) {
						_apply_import(frm, r.message);
					}
				},
			});
		};
		reader.readAsDataURL(file);
	};
	input.click();
}

function _pick_and_import_pdf(frm) {
	const input = document.createElement("input");
	input.type = "file";
	input.accept = ".pdf";
	input.multiple = true;
	input.onchange = function () {
		const files = Array.from(input.files);
		if (!files.length) return;

		const invalid = files.filter(f => !f.name.toLowerCase().endsWith(".pdf"));
		if (invalid.length) {
			frappe.msgprint({ message: __("Seuls les fichiers .pdf sont acceptés."), indicator: "red" });
			return;
		}

		// Lire tous les fichiers en base64
		const readers = files.map(file => new Promise(resolve => {
			const reader = new FileReader();
			reader.onload = e => resolve({
				file_name: file.name,
				file_data: e.target.result.split(",")[1],
			});
			reader.readAsDataURL(file);
		}));

		Promise.all(readers).then(files_data => {
			frappe.call({
				method: "facture_excel.facture_excel.doctype.facture_excel.facture_excel.import_pdf_bl",
				args: { files_data: JSON.stringify(files_data) },
				freeze: true,
				freeze_message: __("Extraction des BL en cours…"),
				callback(r) {
					if (!r.exc && r.message) {
						_apply_import_pdf(frm, r.message);
					}
				},
			});
		});
	};
	input.click();
}

function _apply_import_pdf(frm, result) {
	// Fusionner avec les articles existants (par description normalisée)
	const normalize = s => s.toLowerCase().trim().replace(/\s+/g, " ");

	// Index des articles existants par description normalisée
	const existing = {};
	(frm.doc.items || []).forEach(row => {
		const key = normalize(row.description || "");
		if (key) existing[key] = row;
	});

	let added = 0, merged_count = 0;

	result.items.forEach(item => {
		const key = normalize(item.description);
		if (existing[key]) {
			// Fusion : prix pondéré + somme quantités
			const row = existing[key];
			const old_qty  = flt(row.qty);
			const old_rate = flt(row.rate);
			const new_qty  = flt(item.qty);
			const new_rate = flt(item.rate);
			const total_qty = old_qty + new_qty;
			const new_rate_pond = total_qty > 0
				? Math.round(((old_qty * old_rate) + (new_qty * new_rate)) / total_qty * 100) / 100
				: new_rate;
			frappe.model.set_value(row.doctype, row.name, "qty", total_qty);
			frappe.model.set_value(row.doctype, row.name, "rate", new_rate_pond);
			frappe.model.set_value(row.doctype, row.name, "amount", Math.round(total_qty * new_rate_pond * 100) / 100);
			merged_count++;
		} else {
			// Nouvel article
			const row = frm.add_child("items");
			row.description = item.description;
			row.qty         = item.qty;
			row.rate        = item.rate;
			row.amount      = item.amount;
			existing[key]   = row;
			added++;
		}
	});

	frm.refresh_field("items");
	_calc_total(frm);

	// Résumé
	let msg = `<b>${result.files}</b> BL traité(s) — <b>${result.imported}</b> article(s) extrait(s).<br>`;
	msg += `<b>${added}</b> ajouté(s), <b>${merged_count}</b> fusionné(s) avec articles existants.`;
	if (result.skipped && result.skipped.length > 0) {
		msg += `<br><br><b>${result.skipped.length}</b> problème(s) :<ul>`;
		result.skipped.forEach(s => {
			msg += `<li>${s.file ? s.file + " : " : ""}${s.reason}</li>`;
		});
		msg += "</ul>";
	}
	frappe.msgprint({
		title: __("Résultat de l'import BL"),
		message: msg,
		indicator: result.skipped && result.skipped.length > 0 ? "orange" : "green",
	});
}

function _apply_import(frm, result) {
	// Replace all existing items
	frm.clear_table("items");
	result.items.forEach(item => {
		const row = frm.add_child("items");
		row.description = item.description;
		row.qty         = item.qty;
		row.rate        = item.rate;
		row.amount      = item.amount;
	});
	frm.refresh_field("items");
	_calc_total(frm);

	// Build summary message
	let msg = `<b>${result.imported}</b> article(s) importé(s).`;
	if (result.skipped && result.skipped.length > 0) {
		msg += `<br><br><b>${result.skipped.length}</b> ligne(s) ignorée(s) :`;
		msg += "<ul>";
		result.skipped.forEach(s => {
			msg += `<li>Ligne ${s.row} : ${s.reasons.join(", ")}</li>`;
		});
		msg += "</ul>";
	}
	frappe.msgprint({
		title: __("Résultat de l'import"),
		message: msg,
		indicator: result.skipped && result.skipped.length > 0 ? "orange" : "green",
	});
}

function _download_template() {
	frappe.call({
		method: "facture_excel.facture_excel.doctype.facture_excel.facture_excel.download_template",
		callback(r) {
			if (!r.exc && r.message) {
				const a = document.createElement("a");
				a.href = "data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64," + r.message;
				a.download = "modele_facture_excel.xlsx";
				a.click();
			}
		},
	});
}
