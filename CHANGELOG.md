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
