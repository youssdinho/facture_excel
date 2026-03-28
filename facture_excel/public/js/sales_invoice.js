// Bouton Facture Excel dans le formulaire Sales Invoice

frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		if (frm.doc.docstatus !== 1) return;

		frappe.db.get_value(
			"Facture Excel",
			{ sales_invoice: frm.doc.name, docstatus: ["<", 2] },
			"name",
			function (r) {
				if (r && r.name) {
					frm.add_custom_button(__("Voir Fac. Excel"), function () {
						frappe.set_route("Form", "Facture Excel", r.name);
					}, __("Create"));
				} else {
					frm.add_custom_button(__("Fac. Excel"), function () {
						frappe.route_options = { sales_invoice: frm.doc.name };
						frappe.new_doc("Facture Excel");
					}, __("Create"));
				}
			}
		);
	},
});
