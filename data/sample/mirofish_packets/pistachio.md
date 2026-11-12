# Fiche tendance : Pistache (Pistachio)

- **Identifiant** : `pistachio`
- **Famille aromatique** : fruits_a_coque
- **Rayon (supermarché 3D)** : Snacking sucré & confiserie
- **Zone et période** : monde entier (recherches en anglais), historique Google Trends sur 5 ans ; presse et réseaux sur les 30 derniers jours. Données au 2026-11-12.
- **Origine** : données réelles collectées par le pipeline FlavorTrends. Aucune citation n'est inventée.

## 1. Signaux quantitatifs

- Recherches Google (13 dernières semaines vs les 13 précédentes) : -9 %
- Recherches Google vs la même période l'an dernier : -10 %
- Irrégularité de la courbe (volatilité sur 26 semaines) : 0.11 (0 = régulière)
- Wikipédia, croissance sur 12 mois relative aux autres arômes : -9 points
- Produits Open Food Facts citant l'arôme : 225 produits, 150 marques, 45 pays (échantillon des produits récemment mis à jour, monde entier)
- Mentions sur 30 jours : 13 dans la presse, 95 sur les réseaux (YouTube, Bluesky) ; 230 vues YouTube

## 2. Résultat statistique (modèle V2)

- **Statut** : Stable
- **Probabilité que la hausse soit durable** : non calculée (arôme pas en hausse)
- Fiabilité du modèle : accuracy 82%, F1 0.88, ROC AUC 0.81 sur 82 cas réels, validation leave-one-flavor-out (chaque arôme est prédit par un modèle qui ne l'a jamais vu).

## 3. Preuves : articles et vidéos réels (30 derniers jours)

- [google_news] 2026-11-12 : « Gym Bod adds Pistachio Choc Top Protein Ice Cream »
- [rss] 2026-11-11 : « Pandan rises as a standout in global flavor trends »
- [google_news] 2026-11-11 : « Pickle beer to pistachio spritzes: Food flavours shake up drinks »
- [rss] 2026-11-11 : « Táche debutes Peppermint Mocha Barista »
- [google_news] 2026-11-11 : « Táche Launches Chocolate Pistachio Milk Peppermint Mocha »
- [google_news] 2026-11-11 : « Táche Debuts Its First-Ever Chocolate Pistachio Milk, Reimagining the Classic Peppermint Mocha »

## 4. Points de vigilance (calculés à partir des données)

- Les vues Wikipédia baissent globalement (≈ -24 % en un an) : seule la croissance relative est interprétable.

## 5. Question de simulation

Simuler, sur 12 mois, la réaction de quatre profils de consommateurs (jeune adulte curieux de nouveautés, parent qui fait les courses de la semaine, consommateur attentif à la santé et au « clean label », acheteur de la grande distribution) au lancement de produits à l'arôme **Pistache** dans le rayon « Snacking sucré & confiserie ». En s'appuyant sur les signaux et les points de vigilance ci-dessus, l'arôme dépasse-t-il l'effet de curiosité des premières semaines ? Quels arguments favorisent ou freinent le réachat ?
