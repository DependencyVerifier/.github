# Plan — Console step 6 : notifications

> Plan approuvé, résumé. L'avancement est dans [`console-step-6-status.md`](console-step-6-status.md), les décisions dans `cadrage.md` (58 à 66), le contrat des webhooks dans [`webhook.md`](../webhook.md).

## Contexte

Les steps 4 et 5 produisent et montrent les Findings, mais personne n'est prévenu : il faut ouvrir la console. Le
step 6 remplit le contexte `Notification` (MVP §10.7).

**Choix** : email + webhook signé (Slack, Teams et Discord plus tard) ; destinataires : les abonnés et les comptes
« notification seule » ; événements : vulnérabilités, fins de vie et obsolescence, agents, acceptations de risque ;
digests et contrôles par commandes cron.

## Lots

1. **Événements et contrats** : `FindingChanged` (avec `escalated`), `GetFindingDigests`, `ListExpiringAcceptances`
   (Exposure) ; `AgentAwaitingApproval`, `ListSilentAgents` (Fleet) ; `FilterRecipients` (Organization) ; file
   `notifications`.
2. **Domain et Application** : `NotificationRule` (périmètre, seuils), `WebhookChannel`, `Subscription`, `Notice` et
   `Delivery` (outbox) ; `NoticeWriter` (règles → livraisons, filtrage par visibilité) ; contrôles cron.
3. **Envoi** : email immédiat et digest (désinscription signée), webhook signé (`HttpWebhookCaller`), commandes
   `app:notification:check` et `app:notification:digest`.
4. **Comptes « notification seule »** : invitation d'une adresse, confirmation par lien, puis compte, membership et
   abonnement ; quota ; promotion par invitation ou premier `TEAM_ADMIN`.
5. **Interface** : section Notifications de l'équipe (webhooks, règles du parc, mon abonnement), onglet Notifications
   du projet (règles, destinataires, mon abonnement).
6. **Documentation**.

## Écarts au plan d'origine

- Webhooks toujours immédiats (seuls les emails suivent la fréquence de l'abonnement).
- `notifications-check` toutes les 5 minutes (il relance aussi les livraisons dues).
- Un destinataire ajouté par email reste une invitation jusqu'à sa confirmation (revue de sécurité : ni accaparement
  d'adresse ni énumération des comptes).
