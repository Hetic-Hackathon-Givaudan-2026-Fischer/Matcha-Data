# Fiche tendance : Barbe à papa (Cotton candy)

- **Identifiant** : `cotton_candy`
- **Famille aromatique** : gourmand
- **Rayon (supermarché 3D)** : Snacking sucré & confiserie
- **Zone et période** : monde entier (recherches en anglais), historique Google Trends sur 5 ans ; presse et réseaux sur les 30 derniers jours. Données au 2026-11-12.
- **Origine** : données réelles collectées par le pipeline FlavorTrends. Aucune citation n'est inventée.

## 1. Signaux quantitatifs

- Recherches Google (13 dernières semaines vs les 13 précédentes) : -7 %
- Recherches Google vs la même période l'an dernier : +27 %
- Irrégularité de la courbe (volatilité sur 26 semaines) : 0.13 (0 = régulière)
- Wikipédia, croissance sur 12 mois relative aux autres arômes : -6 points
- Produits Open Food Facts citant l'arôme : 6 produits, 4 marques, 4 pays (échantillon des produits récemment mis à jour, monde entier)
- Mentions sur 30 jours : 3 dans la presse, 80 sur les réseaux (YouTube, Bluesky) ; 1 133 vues YouTube

## 2. Résultat statistique (modèle V2)

- **Statut** : Stable
- **Probabilité que la hausse soit durable** : non calculée (arôme pas en hausse)
- Fiabilité du modèle : accuracy 82%, F1 0.88, ROC AUC 0.81 sur 82 cas réels, validation leave-one-flavor-out (chaque arôme est prédit par un modèle qui ne l'a jamais vu).

## 3. Preuves : articles et vidéos réels (30 derniers jours)

- [google_news] 2026-11-11 : « « Un spectacle entre cuisine et magie » : à Concarneau, la barbe à papa reste la reine de la foire Saint-Martin »
- [google_news] 2026-11-10 : « Artisan Cotton Candy Back At EPCOT’s China Pavilion »
- [youtube] 2026-11-09 : « Why Cigar Reviews Taste Like Peanut Butter & Jelly #shorts »
- [google_news] 2026-11-08 : « The Chemistry of Making Cotton Candy »
- [youtube] 2026-11-05 : « Cotton Candy Loaded Tea🔥 »

## 4. Points de vigilance (calculés à partir des données)

- Peu de produits en rayon dans notre échantillon Open Food Facts (6) : marché encore étroit (ou arôme de niche).
- Les vues Wikipédia baissent globalement (≈ -24 % en un an) : seule la croissance relative est interprétable.

## 5. Question de simulation

Simuler, sur 12 mois, la réaction de quatre profils de consommateurs (jeune adulte curieux de nouveautés, parent qui fait les courses de la semaine, consommateur attentif à la santé et au « clean label », acheteur de la grande distribution) au lancement de produits à l'arôme **Barbe à papa** dans le rayon « Snacking sucré & confiserie ». En s'appuyant sur les signaux et les points de vigilance ci-dessus, l'arôme dépasse-t-il l'effet de curiosité des premières semaines ? Quels arguments favorisent ou freinent le réachat ?
