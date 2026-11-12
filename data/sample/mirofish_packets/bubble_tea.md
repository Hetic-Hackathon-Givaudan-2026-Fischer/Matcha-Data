# Fiche tendance : Bubble tea (Bubble tea)

- **Identifiant** : `bubble_tea`
- **Famille aromatique** : the
- **Types de produits** : Boissons (87 %), Biscuits et pâtisseries (13 %)
- **Zone et période** : monde entier (recherches en anglais), historique Google Trends sur 5 ans ; presse et réseaux sur les 30 derniers jours. Données au 2026-11-12.
- **Origine** : données réelles collectées par le pipeline FlavorTrends. Aucune citation n'est inventée.

## 1. Signaux quantitatifs

- Recherches Google (13 dernières semaines vs les 13 précédentes) : -31 %
- Recherches Google vs la même période l'an dernier : -24 %
- Irrégularité de la courbe (volatilité sur 26 semaines) : 0.23 (0 = régulière)
- Wikipédia, croissance sur 12 mois relative aux autres arômes : -14 points
- Produits Open Food Facts citant l'arôme : 17 produits, 11 marques, 9 pays (échantillon des produits récemment mis à jour, monde entier)
- Mentions sur 30 jours : 8 dans la presse, 44 sur les réseaux (YouTube, Bluesky) ; 99 770 vues YouTube

## 2. Résultat statistique (modèle V2)

- **Statut** : En baisse
- **Probabilité que la hausse soit durable** : non calculée (arôme pas en hausse)
- Fiabilité du modèle : accuracy 82%, F1 0.88, ROC AUC 0.81 sur 82 cas réels, validation leave-one-flavor-out (chaque arôme est prédit par un modèle qui ne l'a jamais vu).

## 3. Preuves : articles et vidéos réels (30 derniers jours)

- [google_news] 2026-11-11 : « Vietnamese sandwich and bubble tea restaurant opens in Lake Norman retail center »
- [google_news] 2026-11-11 : « How a Taiwan Bubble Tea Maker Reached a Paris Sustainability Final -- with Rice and Four Returning Species »
- [youtube] 2026-11-11 : « You asked for taro… and we've had it this whole time 💜😌 Plus a whole lineup of other flavours to »
- [google_news] 2026-11-10 : « ‘Sip Lab’ boba tea shop opens in Orono »
- [google_news] 2026-11-10 : « Bubble Tea Market Study Highlights How Industry Demand Is Evolving »
- [google_news] 2026-11-10 : « China bubble tea chain Mixue shuts more stores as growth model falters »

## 4. Points de vigilance (calculés à partir des données)

- Peu de produits en rayon dans notre échantillon Open Food Facts (17) : marché encore étroit (ou arôme de niche).
- Les vues Wikipédia baissent globalement (≈ -24 % en un an) : seule la croissance relative est interprétable.

## 5. Question de simulation

Simuler, sur 12 mois, la réaction de quatre profils de consommateurs (jeune adulte curieux de nouveautés, parent qui fait les courses de la semaine, consommateur attentif à la santé et au « clean label », acheteur de la grande distribution) au lancement de produits à l'arôme **Bubble tea** dans le rayon « Boissons ». En s'appuyant sur les signaux et les points de vigilance ci-dessus, l'arôme dépasse-t-il l'effet de curiosité des premières semaines ? Quels arguments favorisent ou freinent le réachat ?
