// Bouton "Ajouter Fac. Excel" + colonne Fac. Excel dans la liste Sales Invoice

frappe.listview_settings["Sales Invoice"] = frappe.listview_settings["Sales Invoice"] || {};

// Colonne Fac. Excel : OUI en vert, NON en gris
frappe.listview_settings["Sales Invoice"].formatters = Object.assign(
	frappe.listview_settings["Sales Invoice"].formatters || {},
	{
		fac_com: function (value) {
			if (value === "OUI") {
				return `<span style="color:#28a745;font-weight:700;">OUI</span>`;
			}
			return `<span style="color:#aaa;">NON</span>`;
		},
	}
);

(function () {
	const _orig = frappe.listview_settings["Sales Invoice"].onload;

	frappe.listview_settings["Sales Invoice"].onload = function (listview) {
		if (_orig) _orig.call(this, listview);

		listview.page.add_action_item(__("Ajouter Fac. Excel"), function () {
			const sel = listview.get_checked_items();
			if (sel.length !== 1) {
				frappe.msgprint({
					message: __("Sélectionnez exactement une facture pour créer une Facture Excel."),
					indicator: "orange",
				});
				return;
			}
			const si = sel[0];
			if (si.docstatus !== 1) {
				frappe.msgprint({
					message: __("La facture sélectionnée doit être soumise (validée)."),
					indicator: "red",
				});
				return;
			}
			frappe.route_options = { sales_invoice: si.name };
			frappe.new_doc("Facture Excel");
		});
	};
})();
