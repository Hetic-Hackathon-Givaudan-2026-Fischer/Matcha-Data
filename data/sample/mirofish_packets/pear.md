# Fiche tendance : Poire (Pear)

- **Identifiant** : `pear`
- **Famille aromatique** : fruits_frais
- **Rayon (supermarché 3D)** : Boissons
- **Zone et période** : monde entier (recherches en anglais), historique Google Trends sur 5 ans ; presse et réseaux sur les 30 derniers jours. Données au 2026-11-12.
- **Origine** : données réelles collectées par le pipeline FlavorTrends. Aucune citation n'est inventée.

## 1. Signaux quantitatifs

- Recherches Google (13 dernières semaines vs les 13 précédentes) : +10 %
- Recherches Google vs la même période l'an dernier : -1 %
- Irrégularité de la courbe (volatilité sur 26 semaines) : 0.13 (0 = régulière)
- Wikipédia, croissance sur 12 mois relative aux autres arômes : +5 points
- Produits Open Food Facts citant l'arôme : 196 produits, 103 marques, 27 pays (échantillon des produits récemment mis à jour, monde entier)
- Mentions sur 30 jours : 11 dans la presse, 105 sur les réseaux (YouTube, Bluesky) ; 465 vues YouTube

## 2. Résultat statistique (modèle V2)

- **Statut** : Stable
- **Probabilité que la hausse soit durable** : non calculée (arôme pas en hausse)
- Fiabilité du modèle : accuracy 82%, F1 0.88, ROC AUC 0.81 sur 82 cas réels, validation leave-one-flavor-out (chaque arôme est prédit par un modèle qui ne l'a jamais vu).

## 3. Preuves : articles et vidéos réels (30 derniers jours)

- [google_news] 2026-11-10 : « LA RECETTE DU JOUR : Poêlée de poire avec son crumble »
- [google_news] 2026-11-09 : « Find your ‘Pear’: Dating app by college students to launch in December »
- [google_news] 2026-11-09 : « Vacuum Concentration Improves Pear Wine Quality »
- [google_news] 2026-11-08 : « Update: Pear Fire in Humboldt County - Nov. 8 status »
- [google_news] 2026-11-07 : « Pot-au-feu, consommé Célestine, endives au jambon et poire Belle-Hélène »
- [google_news] 2026-11-06 : « Breaking: Pear Fire reported in Humboldt County on Nov. 6 »

## 4. Points de vigilance (calculés à partir des données)

- Les vues Wikipédia baissent globalement (≈ -24 % en un an) : seule la croissance relative est interprétable.

## 5. Question de simulation

Simuler, sur 12 mois, la réaction de quatre profils de consommateurs (jeune adulte curieux de nouveautés, parent qui fait les courses de la semaine, consommateur attentif à la santé et au « clean label », acheteur de la grande distribution) au lancement de produits à l'arôme **Poire** dans le rayon « Boissons ». En s'appuyant sur les signaux et les points de vigilance ci-dessus, l'arôme dépasse-t-il l'effet de curiosité des premières semaines ? Quels arguments favorisent ou freinent le réachat ?
