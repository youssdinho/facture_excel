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
		title: __("Importer des articles depuis Excel"),
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "description_html",
				options: `<div style="margin-bottom:12px;color:#555;line-height:1.6;">
					Importez vos articles depuis un fichier <b>.xlsx</b>.<br>
					Les colonnes doivent contenir : <b>Désignation</b>, <b>Quantité</b> et <b>Prix Unitaire</b>
					(noms flexibles acceptés).<br>
					<span style="color:#e74c3c;">⚠ L'import remplace tous les articles existants.</span>
				</div>`,
			},
		],
		primary_action_label: __("Importer un fichier"),
		primary_action() {
			d.hide();
			_pick_and_import(frm);
		},
		secondary_action_label: __("Télécharger le modèle"),
		secondary_action() {
			_download_template();
		},
	});
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
