# Fiche tendance : Ail noir (Black garlic)

- **Identifiant** : `black_garlic`
- **Famille aromatique** : umami
- **Rayon (supermarché 3D)** : Épicerie salée & sauces
- **Zone et période** : monde entier (recherches en anglais), historique Google Trends sur 5 ans ; presse et réseaux sur les 30 derniers jours. Données au 2026-11-12.
- **Origine** : données réelles collectées par le pipeline FlavorTrends. Aucune citation n'est inventée.

## 1. Signaux quantitatifs

- Recherches Google (13 dernières semaines vs les 13 précédentes) : -10 %
- Recherches Google vs la même période l'an dernier : +35 %
- Irrégularité de la courbe (volatilité sur 26 semaines) : 0.19 (0 = régulière)
- Wikipédia, croissance sur 12 mois relative aux autres arômes : -18 points
- Produits Open Food Facts citant l'arôme : 9 produits, 4 marques, 4 pays (échantillon des produits récemment mis à jour, monde entier)
- Mentions sur 30 jours : 4 dans la presse, 5 sur les réseaux (YouTube, Bluesky) ; 1 940 vues YouTube

## 2. Résultat statistique (modèle V2)

- **Statut** : Stable
- **Probabilité que la hausse soit durable** : non calculée (arôme pas en hausse)
- Fiabilité du modèle : accuracy 82%, F1 0.88, ROC AUC 0.81 sur 82 cas réels, validation leave-one-flavor-out (chaque arôme est prédit par un modèle qui ne l'a jamais vu).

## 3. Preuves : articles et vidéos réels (30 derniers jours)

- [youtube] 2026-11-10 : « Wrapping up the POLYSHED build | Tasting Black Garlic for the first time »
- [google_news] 2026-11-08 : « Black garlic named flavour of the year for 2027 in food trends report »
- [google_news] 2026-11-06 : « Why is black garlic the 2027 flavor of the year? The ingredient’s rise started in a surprising place »
- [google_news] 2026-11-06 : « Black garlic finally broke out of restaurant kitchens, and 2027 could decide if it becomes a staple »
- [google_news] 2026-11-05 : « ‘Bob’s Burgers’ treated black garlic like a secret weapon in 2014. Now it’s the 2027 flavor of the year »

## 4. Points de vigilance (calculés à partir des données)

- Peu de produits en rayon dans notre échantillon Open Food Facts (9) : marché encore étroit (ou arôme de niche).
- 11 % des mentions récentes sont sponsorisées : signal en partie marketing.
- Peu de mentions récentes dans la presse et les réseaux (9 sur 30 jours) : confiance limitée.
- Les vues Wikipédia baissent globalement (≈ -24 % en un an) : seule la croissance relative est interprétable.

## 5. Question de simulation

Simuler, sur 12 mois, la réaction de quatre profils de consommateurs (jeune adulte curieux de nouveautés, parent qui fait les courses de la semaine, consommateur attentif à la santé et au « clean label », acheteur de la grande distribution) au lancement de produits à l'arôme **Ail noir** dans le rayon « Épicerie salée & sauces ». En s'appuyant sur les signaux et les points de vigilance ci-dessus, l'arôme dépasse-t-il l'effet de curiosité des premières semaines ? Quels arguments favorisent ou freinent le réachat ?
