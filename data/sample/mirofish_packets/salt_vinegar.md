# Fiche tendance : Sel et vinaigre (Salt and vinegar)

- **Identifiant** : `salt_vinegar`
- **Famille aromatique** : umami
- **Rayon (supermarché 3D)** : Boissons
- **Zone et période** : monde entier (recherches en anglais), historique Google Trends sur 5 ans ; presse et réseaux sur les 30 derniers jours. Données au 2026-11-12.
- **Origine** : données réelles collectées par le pipeline FlavorTrends. Aucune citation n'est inventée.

## 1. Signaux quantitatifs

- Recherches Google (13 dernières semaines vs les 13 précédentes) : n.d.
- Recherches Google vs la même période l'an dernier : n.d.
- Irrégularité de la courbe (volatilité sur 26 semaines) : n.d. (0 = régulière)
- Wikipédia, croissance sur 12 mois relative aux autres arômes : n.d.
- Produits Open Food Facts citant l'arôme : 13 produits, 9 marques, 7 pays (échantillon des produits récemment mis à jour, monde entier)
- Mentions sur 30 jours : 1 dans la presse, 15 sur les réseaux (YouTube, Bluesky) ; 1 vues YouTube

## 2. Résultat statistique (modèle V2)

- **Statut** : Volume de recherche trop faible pour conclure
- **Probabilité que la hausse soit durable** : non calculée (arôme pas en hausse)
- Fiabilité du modèle : accuracy 82%, F1 0.88, ROC AUC 0.81 sur 82 cas réels, validation leave-one-flavor-out (chaque arôme est prédit par un modèle qui ne l'a jamais vu).

## 3. Preuves : articles et vidéos réels (30 derniers jours)

- [youtube] 2026-11-09 : « Lay's All Dressed chips: the Canadian flavor you've never had »
- [google_news] 2026-11-06 : « We tasted supermarket salt and vinegar crisps to find the best for tang and crunch »

## 4. Points de vigilance (calculés à partir des données)

- Volume de recherche Google Trends trop faible pour mesurer une tendance fiable.
- Peu de produits en rayon dans notre échantillon Open Food Facts (13) : marché encore étroit (ou arôme de niche).
- Les vues Wikipédia baissent globalement (≈ -24 % en un an) : seule la croissance relative est interprétable.

## 5. Question de simulation

Simuler, sur 12 mois, la réaction de quatre profils de consommateurs (jeune adulte curieux de nouveautés, parent qui fait les courses de la semaine, consommateur attentif à la santé et au « clean label », acheteur de la grande distribution) au lancement de produits à l'arôme **Sel et vinaigre** dans le rayon « Boissons ». En s'appuyant sur les signaux et les points de vigilance ci-dessus, l'arôme dépasse-t-il l'effet de curiosité des premières semaines ? Quels arguments favorisent ou freinent le réachat ?
