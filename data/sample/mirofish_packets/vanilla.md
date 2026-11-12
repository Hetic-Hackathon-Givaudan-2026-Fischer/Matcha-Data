# Fiche tendance : Vanille (Vanilla)

- **Identifiant** : `vanilla`
- **Famille aromatique** : gourmand
- **Types de produits** : Chocolats et produits chocolatés (20 %), Biscuits et pâtisseries (20 %), Glaces et desserts glacés (15 %), Produits nutritionnels et sportifs (10 %)
- **Zone et période** : monde entier (recherches en anglais), historique Google Trends sur 5 ans ; presse et réseaux sur les 30 derniers jours. Données au 2026-11-12.
- **Origine** : données réelles collectées par le pipeline FlavorTrends. Aucune citation n'est inventée.

## 1. Signaux quantitatifs

- Recherches Google (13 dernières semaines vs les 13 précédentes) : -10 %
- Recherches Google vs la même période l'an dernier : +9 %
- Irrégularité de la courbe (volatilité sur 26 semaines) : 0.13 (0 = régulière)
- Wikipédia, croissance sur 12 mois relative aux autres arômes : +6 points
- Produits Open Food Facts citant l'arôme : 2188 produits, 1016 marques, 92 pays (échantillon des produits récemment mis à jour, monde entier)
- Mentions sur 30 jours : 15 dans la presse, 231 sur les réseaux (YouTube, Bluesky) ; 18 585 vues YouTube

## 2. Résultat statistique (modèle V2)

- **Statut** : Stable
- **Probabilité que la hausse soit durable** : non calculée (arôme pas en hausse)
- Fiabilité du modèle : accuracy 82%, F1 0.88, ROC AUC 0.81 sur 82 cas réels, validation leave-one-flavor-out (chaque arôme est prédit par un modèle qui ne l'a jamais vu).

## 3. Preuves : articles et vidéos réels (30 derniers jours)

- [google_news] 2026-11-11 : « Coca-Cola : un Zéro vanille et crème pour Noël arrive en France, 300 000 caisses prévues »
- [google_news] 2026-11-11 : « Coca-Cola lance une nouvelle saveur en édition limitée pour Noël censée rappeler le goût de la glace vanille »
- [google_news] 2026-11-10 : « Australia’s best vanilla ice cream, ranked »
- [youtube] 2026-11-10 : « I Put a Little Debbie Christmas Tree Cake in My COFFEE?! 🤯🎄 »
- [rss] 2026-11-10 : « Shamrock Farms debuts Santa's Favorite Milk »
- [google_news] 2026-11-10 : « Test Vahiné : 1’000 gousses de vanille Bourbon de Madagascar gratuites »

## 4. Points de vigilance (calculés à partir des données)

- Les vues Wikipédia baissent globalement (≈ -24 % en un an) : seule la croissance relative est interprétable.

## 5. Question de simulation

Simuler, sur 12 mois, la réaction de quatre profils de consommateurs (jeune adulte curieux de nouveautés, parent qui fait les courses de la semaine, consommateur attentif à la santé et au « clean label », acheteur de la grande distribution) au lancement de produits à l'arôme **Vanille** dans le rayon « Chocolats et produits chocolatés ». En s'appuyant sur les signaux et les points de vigilance ci-dessus, l'arôme dépasse-t-il l'effet de curiosité des premières semaines ? Quels arguments favorisent ou freinent le réachat ?
