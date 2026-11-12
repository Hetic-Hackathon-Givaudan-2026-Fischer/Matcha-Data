# Fiche tendance : Curry (Curry)

- **Identifiant** : `curry`
- **Famille aromatique** : epice
- **Rayon (supermarché 3D)** : Épicerie salée & sauces
- **Zone et période** : monde entier (recherches en anglais), historique Google Trends sur 5 ans ; presse et réseaux sur les 30 derniers jours. Données au 2026-11-12.
- **Origine** : données réelles collectées par le pipeline FlavorTrends. Aucune citation n'est inventée.

## 1. Signaux quantitatifs

- Recherches Google (13 dernières semaines vs les 13 précédentes) : +27 %
- Recherches Google vs la même période l'an dernier : +56 %
- Irrégularité de la courbe (volatilité sur 26 semaines) : 0.59 (0 = régulière)
- Wikipédia, croissance sur 12 mois relative aux autres arômes : +3 points
- Produits Open Food Facts citant l'arôme : 361 produits, 226 marques, 42 pays (échantillon des produits récemment mis à jour, monde entier)
- Mentions sur 30 jours : 22 dans la presse, 195 sur les réseaux (YouTube, Bluesky) ; 50 327 vues YouTube

## 2. Résultat statistique (modèle V2)

- **Statut** : En hausse : probablement passager (buzz)
- **Probabilité que la hausse soit durable** : 13%
- Fiabilité du modèle : accuracy 82%, F1 0.88, ROC AUC 0.81 sur 82 cas réels, validation leave-one-flavor-out (chaque arôme est prédit par un modèle qui ne l'a jamais vu).

## 3. Preuves : articles et vidéos réels (30 derniers jours)

- [google_news] 2026-11-12 : « Weston-super-Mare curry house owner recognised for tackling major issue »
- [google_news] 2026-11-12 : « Warriors’ Stephen Curry exits early with abdominal soreness, ruled out vs Rockets »
- [google_news] 2026-11-11 : « Glasgow restaurant creates 'curry in a pie' for Aldi stores across Scotland »
- [google_news] 2026-11-11 : « LEON UNVEILS CHRISTMAS 2026 MENU WITH FESTIVE WRAP, SANDO CLAUS AND RETURNING CHRISTMAS PARTY CURRY! »
- [google_news] 2026-11-11 : « Glasgow Indian restaurant teams up with popular bakery to launch new curry pies »
- [youtube] 2026-11-10 : « Singapore Noodles The Takeaway Classic »

## 4. Points de vigilance (calculés à partir des données)

- Courbe de recherche irrégulière (volatilité 0.59) : risque d'effet de mode.
- Pic récent marqué (pic = 3.8 × la moyenne) : forme typique d'un buzz.
- Les vues Wikipédia baissent globalement (≈ -24 % en un an) : seule la croissance relative est interprétable.

## 5. Question de simulation

Simuler, sur 12 mois, la réaction de quatre profils de consommateurs (jeune adulte curieux de nouveautés, parent qui fait les courses de la semaine, consommateur attentif à la santé et au « clean label », acheteur de la grande distribution) au lancement de produits à l'arôme **Curry** dans le rayon « Épicerie salée & sauces ». En s'appuyant sur les signaux et les points de vigilance ci-dessus, l'arôme dépasse-t-il l'effet de curiosité des premières semaines ? Quels arguments favorisent ou freinent le réachat ?
