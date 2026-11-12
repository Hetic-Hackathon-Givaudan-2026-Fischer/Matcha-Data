# Fiche tendance : Framboise (Raspberry)

- **Identifiant** : `raspberry`
- **Famille aromatique** : fruits_rouges
- **Rayon (supermarché 3D)** : Boissons
- **Zone et période** : monde entier (recherches en anglais), historique Google Trends sur 5 ans ; presse et réseaux sur les 30 derniers jours. Données au 2026-11-12.
- **Origine** : données réelles collectées par le pipeline FlavorTrends. Aucune citation n'est inventée.

## 1. Signaux quantitatifs

- Recherches Google (13 dernières semaines vs les 13 précédentes) : -27 %
- Recherches Google vs la même période l'an dernier : -19 %
- Irrégularité de la courbe (volatilité sur 26 semaines) : 0.22 (0 = régulière)
- Wikipédia, croissance sur 12 mois relative aux autres arômes : -2 points
- Produits Open Food Facts citant l'arôme : 504 produits, 305 marques, 46 pays (échantillon des produits récemment mis à jour, monde entier)
- Mentions sur 30 jours : 7 dans la presse, 125 sur les réseaux (YouTube, Bluesky) ; 6 436 vues YouTube

## 2. Résultat statistique (modèle V2)

- **Statut** : En baisse
- **Probabilité que la hausse soit durable** : non calculée (arôme pas en hausse)
- Fiabilité du modèle : accuracy 82%, F1 0.88, ROC AUC 0.81 sur 82 cas réels, validation leave-one-flavor-out (chaque arôme est prédit par un modèle qui ne l'a jamais vu).

## 3. Preuves : articles et vidéos réels (30 derniers jours)

- [google_news] 2026-11-10 : « Pokhvalinka Raspberry: Large Berries on First-Year Canes Require Consistent Watering »
- [google_news] 2026-11-10 : « GODIVA Has New Raspberry Ganache Chocolates at Target and Walmart »
- [google_news] 2026-11-10 : « Doctor shares recipe for no-bake chocolate raspberry cups loaded with healthy fibre and antioxidants | Hindustan Times »
- [rss] 2026-11-10 : « ZOE Enters Snack Category With Gut Health Bar »
- [youtube] 2026-11-09 : « Häagen-Dazs Mango Raspberry Ice Cream Review | A Perfect Fruity Combo? »
- [youtube] 2026-11-09 : « What EXACTLY Is Blue Raspberry Flavor?! 🫐 »

## 4. Points de vigilance (calculés à partir des données)

- Les vues Wikipédia baissent globalement (≈ -24 % en un an) : seule la croissance relative est interprétable.

## 5. Question de simulation

Simuler, sur 12 mois, la réaction de quatre profils de consommateurs (jeune adulte curieux de nouveautés, parent qui fait les courses de la semaine, consommateur attentif à la santé et au « clean label », acheteur de la grande distribution) au lancement de produits à l'arôme **Framboise** dans le rayon « Boissons ». En s'appuyant sur les signaux et les points de vigilance ci-dessus, l'arôme dépasse-t-il l'effet de curiosité des premières semaines ? Quels arguments favorisent ou freinent le réachat ?
