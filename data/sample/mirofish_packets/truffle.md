# Fiche tendance : Truffe (Truffle)

- **Identifiant** : `truffle`
- **Famille aromatique** : umami
- **Rayon (supermarché 3D)** : Boissons
- **Zone et période** : monde entier (recherches en anglais), historique Google Trends sur 5 ans ; presse et réseaux sur les 30 derniers jours. Données au 2026-11-12.
- **Origine** : données réelles collectées par le pipeline FlavorTrends. Aucune citation n'est inventée.

## 1. Signaux quantitatifs

- Recherches Google (13 dernières semaines vs les 13 précédentes) : n.d.
- Recherches Google vs la même période l'an dernier : n.d.
- Irrégularité de la courbe (volatilité sur 26 semaines) : n.d. (0 = régulière)
- Wikipédia, croissance sur 12 mois relative aux autres arômes : -16 points
- Produits Open Food Facts citant l'arôme : 114 produits, 73 marques, 24 pays (échantillon des produits récemment mis à jour, monde entier)
- Mentions sur 30 jours : 13 dans la presse, 52 sur les réseaux (YouTube, Bluesky) ; 4 616 vues YouTube

## 2. Résultat statistique (modèle V2)

- **Statut** : Volume de recherche trop faible pour conclure
- **Probabilité que la hausse soit durable** : non calculée (arôme pas en hausse)
- Fiabilité du modèle : accuracy 82%, F1 0.88, ROC AUC 0.81 sur 82 cas réels, validation leave-one-flavor-out (chaque arôme est prédit par un modèle qui ne l'a jamais vu).

## 3. Preuves : articles et vidéos réels (30 derniers jours)

- [google_news] 2026-11-10 : « Des bulles chauffées avec raclette et menus à la truffe chez Maison Delano Paris pour l'hiver 2026 »
- [google_news] 2026-11-10 : « Heated domes with raclette and truffle menus at Maison Delano Paris for winter 2026 »
- [google_news] 2026-11-10 : « White truffle season: The best wine to drink with nature’s priciest delicacy »
- [google_news] 2026-11-10 : « Burger King 11.11 Deals: 1-for-1 Whopper, Long Chicken, Truffle Mayo Burgers and More (9 to 15 Nov 2026) »
- [youtube] 2026-11-10 : « Trying Walkers GOLD Crisps Cheddar & Onion, Black Truffle and Sea Salt & Olive Oil »
- [google_news] 2026-11-09 : « White Truffle Sells for 100,000 Euros at Italian Auction »

## 4. Points de vigilance (calculés à partir des données)

- Volume de recherche Google Trends trop faible pour mesurer une tendance fiable.
- Les vues Wikipédia baissent globalement (≈ -24 % en un an) : seule la croissance relative est interprétable.

## 5. Question de simulation

Simuler, sur 12 mois, la réaction de quatre profils de consommateurs (jeune adulte curieux de nouveautés, parent qui fait les courses de la semaine, consommateur attentif à la santé et au « clean label », acheteur de la grande distribution) au lancement de produits à l'arôme **Truffe** dans le rayon « Boissons ». En s'appuyant sur les signaux et les points de vigilance ci-dessus, l'arôme dépasse-t-il l'effet de curiosité des premières semaines ? Quels arguments favorisent ou freinent le réachat ?
