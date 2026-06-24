## [0.0.5] - 2026-06-24

### Ajouté
- **Import BL PDF groupé** : nouveau mode d'import qui conserve chaque Bon de Livraison séparé (n° + date) au lieu de fusionner tous les articles
  - Champs `bl_no` / `bl_date` sur les lignes de Facture Excel
  - Extraction du n° de BL et de la date depuis l'en-tête du PDF
  - Articles reproduits ligne par ligne, sans déduplication entre BL
  - Prix unitaire recalculé depuis le montant ligne (M.TTC) car la colonne PU du PDF est tronquée à l'extraction
  - Remplace tous les articles existants à l'import
  - Print format : affichage groupé avec une ligne d'en-tête par BL
- Le mode **« BL PDF (fusionné) »** existant est conservé

### Corrigé
- **Print format** : le Sous-total HT et la TVA étaient repris de la facture ERPNext liée et ne correspondaient pas au Total TTC commercial. Ils sont désormais calculés à partir du TTC commercial réel (taux de TVA déduit de la facture ERPNext, 20 % par défaut)
- **Print format** : suppression du fond noir sur l'en-tête de BL (économie d'encre), remplacé par un filet et une barre latérale
- **Dialogue d'import** : lien « Télécharger le modèle » déplacé dans la section Excel ; couleurs des boutons d'import harmonisées (seul « BL PDF (fusionné) » mis en avant)

## [0.0.4] - 2026-05-04

### Modifié
- **Prix** : précision des champs prix (Prix Unitaire, Montant, Total Commercial, Total ERPNext) passée de 2 à 5 chiffres après la virgule
- **Calculs** : arrondis internes (import PDF BL et import Excel) mis à jour à 5 décimales
- **Validation** : tolérance d'écart entre total commercial et total ERPNext ajustée à 0,000009

## [0.0.3] - 2026-05-03

### Corrigé
- **Import BL PDF** : une ligne vide (ligne vide par défaut de Frappe) apparaissait en tête du tableau après import. Elle est désormais supprimée avant la fusion des articles.

## [0.0.2] - 2026-05-03

### Corrigé
- **Import BL PDF** : les articles sans référence dans le PDF (colonne Réf vide) étaient ignorés silencieusement. Ils sont désormais inclus en utilisant la désignation comme clé interne de déduplication.

## [0.0.1] - 2026-03-28

### Ajouté
- **DocType Facture Excel** : document commercial lié à une Sales Invoice ERPNext
  - Articles en texte libre (désignation, quantité, prix unitaire, montant)
  - Calcul automatique du total commercial
  - Indicateur d'écart en temps réel avec le total de la facture ERPNext
- **Validation** : total commercial doit être égal au total de la Sales Invoice avant soumission
- **Unicité** : une seule Facture Excel active par Sales Invoice
- **Amend** : support de l'annulation et création de nouvelle version (X → X-1) avec liaison SI préservée
- **Annulation automatique** : si la Sales Invoice est annulée, la Facture Excel liée est annulée automatiquement
- **Colonne Fac. Excel** dans la liste Sales Invoice (OUI en vert / NON en gris)
- **Bouton Fac. Excel** dans le formulaire Sales Invoice (groupe Créer)
- **Bouton Ajouter Fac. Excel** dans le menu Actions de la liste Sales Invoice
- **Format d'impression** "Facture Excel Standard" : Jinja, layout A4, Montserrat, montant en lettres (Dirhams), droit de timbre pour paiement espèce
- **Import Excel** : importation d'articles depuis un fichier .xlsx avec détection flexible des colonnes et rapport d'import
- **Modèle Excel** : téléchargement d'un fichier modèle .xlsx pré-formaté
