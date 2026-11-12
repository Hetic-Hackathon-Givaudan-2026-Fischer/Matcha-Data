# Fiche tendance : Piment (Chili pepper)

- **Identifiant** : `chili`
- **Famille aromatique** : epice
- **Rayon (supermarché 3D)** : Épicerie salée & sauces
- **Zone et période** : monde entier (recherches en anglais), historique Google Trends sur 5 ans ; presse et réseaux sur les 30 derniers jours. Données au 2026-11-12.
- **Origine** : données réelles collectées par le pipeline FlavorTrends. Aucune citation n'est inventée.

## 1. Signaux quantitatifs

- Recherches Google (13 dernières semaines vs les 13 précédentes) : +22 %
- Recherches Google vs la même période l'an dernier : +0 %
- Irrégularité de la courbe (volatilité sur 26 semaines) : 0.15 (0 = régulière)
- Wikipédia, croissance sur 12 mois relative aux autres arômes : +0 points
- Produits Open Food Facts citant l'arôme : 1405 produits, 774 marques, 76 pays (échantillon des produits récemment mis à jour, monde entier)
- Mentions sur 30 jours : 22 dans la presse, 215 sur les réseaux (YouTube, Bluesky) ; 18 240 vues YouTube

## 2. Résultat statistique (modèle V2)

- **Statut** : En hausse saisonnière (niveau proche de l'an dernier)
- **Probabilité que la hausse soit durable** : non calculée (arôme pas en hausse)
- Fiabilité du modèle : accuracy 82%, F1 0.88, ROC AUC 0.81 sur 82 cas réels, validation leave-one-flavor-out (chaque arôme est prédit par un modèle qui ne l'a jamais vu).

## 3. Preuves : articles et vidéos réels (30 derniers jours)

- [google_news] 2026-11-11 : « Tequesta Chili Cook-Off Brings the Heat »
- [google_news] 2026-11-11 : « Veterans Day 2026 deals: Score free food from Olive Garden, Krispy Kreme, Chili’s, and more »
- [google_news] 2026-11-11 : « Kiwanis Chili Day Remembered as Annual Northeast Tradition »
- [google_news] 2026-11-10 : « Barney’s Beanery West Hollywood Celebrates Route 66 Centennial With $1 Chili Special »
- [google_news] 2026-11-10 : « Spiced Soft Drinks: The Root Co. Adds Chipotle Heat to Chilli Ginger Beer »
- [youtube] 2026-11-10 : « Reviewing Eat Real Hummus Chips Zesty Lime Chilli And Sea Salt Flavour »

## 4. Points de vigilance (calculés à partir des données)

- Les vues Wikipédia baissent globalement (≈ -24 % en un an) : seule la croissance relative est interprétable.

## 5. Question de simulation

Simuler, sur 12 mois, la réaction de quatre profils de consommateurs (jeune adulte curieux de nouveautés, parent qui fait les courses de la semaine, consommateur attentif à la santé et au « clean label », acheteur de la grande distribution) au lancement de produits à l'arôme **Piment** dans le rayon « Épicerie salée & sauces ». En s'appuyant sur les signaux et les points de vigilance ci-dessus, l'arôme dépasse-t-il l'effet de curiosité des premières semaines ? Quels arguments favorisent ou freinent le réachat ?
