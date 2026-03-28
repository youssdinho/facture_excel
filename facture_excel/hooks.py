app_name = "facture_excel"
app_title = "Facture Excel"
app_publisher = "Amanatem"
app_description = "Facture Commerciale - Amanatem"
app_email = "me@gmail.com"
app_license = "mit"

# ─────────────────────────────────────────────────────────────────
# DOC EVENTS
# ─────────────────────────────────────────────────────────────────
doc_events = {
	"Sales Invoice": {
		"on_cancel": "facture_excel.facture_excel.doctype.facture_excel.facture_excel.on_sales_invoice_cancel",
	}
}

# ─────────────────────────────────────────────────────────────────
# JAVASCRIPT
# ─────────────────────────────────────────────────────────────────
doctype_js = {
	"Sales Invoice": "public/js/sales_invoice.js",
}

doctype_list_js = {
	"Sales Invoice": "public/js/sales_invoice_list.js",
}

# ─────────────────────────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────────────────────────
fixtures = [
	{
		"dt": "Custom Field",
		"filters": [["module", "=", "Facture Excel"]],
	},
	{
		"dt": "Print Format",
		"filters": [["module", "=", "Facture Excel"]],
	},
]
