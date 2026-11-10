# Plan — Console step 1 : socle Identity, Organization et Audit

> Plan approuvé (révision 23), copié tel quel. L'avancement et les décisions prises depuis sont dans [`console-step-1-status.md`](console-step-1-status.md).

Révision : 23

## Contexte

La console n'est aujourd'hui qu'un squelette :
- ce qui existe : 3 bus Messenger, un healthcheck, le kit UI shadcn et des previews statiques (`/`, `/_preview/login`) ;
- ce qui manque : SecurityBundle, mailer, entités et migrations ;
- tous les contextes (`Identity`, `Organization`, `Audit`…) sont des dossiers vides (`.gitkeep`).

Ce step pose le socle dont tout le reste dépend : se connecter, être autorisé par permission, être tracé, et administrer l'instance, les équipes, les projets et les membres.

À la fin du step :
- un super admin créé en CLI se connecte avec un second facteur ;
- il crée une équipe et invite son premier `TEAM_ADMIN` ;
- ce `TEAM_ADMIN` gère les membres, les projets et les environnements, dans la limite des quotas ;
- chaque action, chaque refus et chaque événement d'authentification est écrit dans un journal d'audit **non modifiable par l'application**. Le rôle runtime ne peut ni modifier ni supprimer d'entrée. Le rôle propriétaire, réservé à la CLI, le peut techniquement. Une preuve d'altération par chaînage des entrées est un non-objectif.

Sources :
- `docs/cadrage.md` : §3, §5, §5ter, §7 et §7bis (catalogue des permissions et règles de garde) ;
- `docs/design.md` : §5 et §6 (écrans d'authentification) ;
- `console/CLAUDE.md` : conventions DDD, CQRS, tests et UI.

La console tourne en **mode worker FrankenPHP** (`frankenphp/Caddyfile` L34). Un service qui garde un état le conserve donc d'une requête à l'autre.

### Décisions prises

Ces décisions ont été prises avec l'utilisateur le 09/11/2026. Le cadrage sera mis à jour en conséquence.

**Périmètre**

1. **Passkeys** : reportées dans un step 1b séparé, hors de ce plan. Le modèle prévoit déjà leur place.

**Connexion et second facteur**

2. **Second facteur à chaque connexion**, pour tout le monde : le TOTP s'il est configuré, sinon un code par email.
   - L'utilisateur peut cocher « Faire confiance à cet appareil ». Le 2FA est alors sauté pendant **30 jours**, **admins compris**.
   - La confiance n'évite que le second facteur, jamais le mot de passe.
3. **Récupération quand on perd son TOTP** :
   - **10 codes de secours** à usage unique, affichés une seule fois et stockés hachés ;
   - ou une **réinitialisation du 2FA par le super admin**, auditée.

   Une fois le TOTP activé, **on ne peut plus se rabattre sur le code email**.
4. **Envoi des emails** : par `MAILER_DSN`, une variable d'environnement de l'exploitant. Mailpit sert en dev. L'écran SMTP d'InstanceSettings est reporté.
5. **Mot de passe** :
   - 12 à 4096 caractères, sans règle de composition ;
   - Argon2id ;
   - il ne doit ni être égal à l'email normalisé, ni le contenir, comparaison faite sans tenir compte de la casse ;
   - aucun appel externe : pas de vérification HIBP.

**Limites, sessions et ré-authentification**

6. **Limitation des échecs**, en fenêtre glissante et sans verrouillage du compte :
   - mot de passe : 5 échecs par 15 min pour un couple compte + IP, et 50 par 15 min pour une IP ;
   - code email : 5 essais par code et 3 renvois par 15 min ;
   - tout est audité.
7. **Sessions** :
   - **30 min d'inactivité** au plus et **12 h** au total ;
   - stockées en PostgreSQL ;
   - cookie `HttpOnly`, `Secure` et `SameSite=Strict` ;
   - pas de « remember me ».
8. **Ré-authentification** si la dernière authentification date de plus de **10 min**, pour les actions sensibles :
   - changer de mot de passe ;
   - gérer le TOTP et les codes de secours ;
   - accorder ou retirer `ROLE_SUPER_ADMIN` ;
   - réinitialiser le 2FA d'un autre compte ;
   - désactiver un compte.

**Invitations et mot de passe oublié**

9. **Invitation sur un projet sans être dans l'équipe** : à l'acceptation, on crée aussi une TeamMembership `TEAM_GUEST`.
   - Il faut la permission `team.members.manage` ou `project.members.manage`.
   - Le quota `maxMembers` s'applique.
10. **Toujours un lien à accepter**, même si le compte existe déjà, pour ne rien révéler à l'invitant.
11. **Cycle de vie d'une invitation** :
    - jeton haché à usage unique, valable **7 jours** ;
    - renvoyable et révocable ;
    - une seule invitation en attente par couple email + cible ;
    - quota vérifié **à l'envoi** (les invitations en attente comptent) **et à l'acceptation**.
12. **Mot de passe oublié** :
    - le message est le même, que le compte existe ou non ;
    - le lien est à usage unique et valable **30 min** ;
    - le 2FA reste exigé après la réinitialisation ;
    - les sessions et les appareils de confiance sont révoqués.

**Équipes, rôles et quotas**

13. **Quotas : le super admin est bloqué lui aussi.** Il doit d'abord relever le quota. Cela corrige le cadrage (§5ter L206, §7bis L703).
14. **Premier `TEAM_ADMIN`** : il est invité au moment de la création de l'équipe.
    - Une équipe sans admin est tolérée tant que l'invitation n'est pas acceptée.
    - Ensuite, l'équipe doit garder au moins un `TEAM_ADMIN`.
15. **Ordre des rôles** : par niveau, et l'on peut attribuer un rôle égal au sien.
    - Équipe : `TEAM_ADMIN` > `TEAM_MEMBER` > `TEAM_VIEWER` > `TEAM_GUEST`.
    - Projet : `PROJECT_ADMIN` > `PROJECT_MEMBER` > `PROJECT_VIEWER`.
    - Un `TEAM_ADMIN` couvre tous les rôles projet de son équipe.
    - Un `PROJECT_ADMIN` peut nommer un autre `PROJECT_ADMIN`, mais ne touche jamais aux rôles d'équipe.
16. **Comptes « notification seule »** : ce sont de vrais `User`, simplement **sans la permission d'instance `account.login`**.
    - Cette permission remplace le champ `loginEnabled`.
    - Ce step livre le modèle et le refus de connexion. Leur création, la confirmation d'email, le désabonnement et le quota `maxNotificationOnlyAccounts` viendront avec le contexte Notification.

**Audit**

17. **Ce que l'audit enregistre** : les commandes métier (succès et échec), les refus d'accès et les événements d'authentification. Les lectures réussies ne sont **pas** enregistrées.
18. **Purge** :
    - `audit_log` est **partitionnée par mois** ;
    - des triggers refusent `UPDATE` et `DELETE` ;
    - la purge détache puis supprime (`DROP`) les partitions plus anciennes que `AUDIT_RETENTION_DAYS` (365 jours par défaut).

**Librairies, UI et livraison**

19. **2FA** : `scheb/2fa-bundle` (TOTP, codes de secours, appareil de confiance). Le code email passe par un **provider maison**, haché et avec un nombre d'essais limité.
20. **UI super admin minimale** :
    - utilisateurs, équipes et quotas, quotas par défaut, audit global ;
    - plus tous les écrans d'équipe.
21. **Suppressions** :
    - les comptes sont désactivés, jamais supprimés ;
    - un projet ou un environnement ne se supprime que s'il est vide ;
    - la suppression d'équipe et l'effacement RGPD sont reportés.
22. **Langue** : UI en anglais via le translator, avec des clés de traduction.
23. **Livraison en 3 commits**, chacun vert sur `make qa` :
    1. Shared et Audit ;
    2. Identity ;
    3. Organization et les écrans.

**Arbitrages du tour 1 de validation**

24. **On garde la décision du 09/11, super admin compris**, contre l'avis du gourou security : tout second facteur est accepté pour les admins, y compris le code par email.
    - Risque accepté et consigné : pour un super admin sans TOTP, la boîte mail devient le seul facteur (réinitialisation par email, code par email, appareil de confiance de 30 jours).
    - Mesure compensatoire : les emails d'alerte de la décision 26.
25. **Deux rôles PostgreSQL.**
    - Le rôle **runtime** (`DATABASE_URL`) n'a que `INSERT` et `SELECT` sur `audit_log`. Il ne peut ni modifier ni supprimer de partition ou de trigger.
    - Le rôle **propriétaire** (`DATABASE_MIGRATIONS_URL`) sert uniquement à la CLI : migrations et `app:audit:maintain-partitions`.
    - Un script d'initialisation du conteneur `database` crée ces deux rôles. La procédure de production est documentée.
26. **Emails d'alerte** envoyés au titulaire du compte quand :
    - son mot de passe change ;
    - son TOTP est activé ou désactivé ;
    - ses codes de secours sont régénérés ;
    - son 2FA est réinitialisé par le super admin ;
    - `ROLE_SUPER_ADMIN` lui est accordé ou retiré ;
    - un nouvel appareil de confiance est enregistré.

  Ces emails ne contiennent aucun lien d'action, seulement « si ce n'est pas vous, contactez l'administrateur ».

**Retours de l'utilisateur à la présentation de la révision 6** (09/11/2026)

27. **Emails en local : Mailpit.**
    - En dev, `MAILER_DSN=smtp://mailpit:1025` pointe vers le service `mailpit` de `compose.override.yaml`. Interface sur http://localhost:8025.
    - En test, `MAILER_DSN=null://null`, avec les assertions Mailer de Symfony.
    - En production, la valeur est fournie par l'exploitant.
28. **Toutes les limitations passent par le composant `symfony/rate-limiter`.**
    - Il n'y a aucun compteur maison.
    - `login_throttling` du firewall s'appuie lui-même sur ce composant.
    - Les limiteurs du second facteur (fenêtres de 15 min et de 24 h), du mot de passe oublié, du renvoi de code email et du renvoi d'invitation sont des `RateLimiterFactory` nommées dans `rate_limiter.yaml` (politique `sliding_window`). Elles ne sont jamais utilisées directement par l'Application, mais toujours via le port `AttemptThrottle` (voir « Limiteurs : mise en œuvre »).
    - Le compteur `attempts` d'un `EmailLoginCode` (5 essais par code) n'est pas un limiteur : c'est un invariant de l'agrégat, qui meurt avec le code.
29. **Sessions en base de données.**
    - Les sessions sont stockées dans PostgreSQL, table `sessions`, par `PdoSessionHandler` sur la connexion `DATABASE_URL`, avec le rôle runtime.
    - La table est créée par une migration, avec ses `GRANT` à `depverify_app`.
    - Aucun handler de session sur fichiers, sauf en test. En test, on utilise `session.storage.factory.mock_file`, et un test d'intégration dédié vérifie le vrai `PdoSessionHandler`.
30. **Mode worker de FrankenPHP aussi en production** (question de l'utilisateur, 09/11/2026).
    - C'est déjà le cas aujourd'hui : le bloc `worker { file ./public/index.php }` est dans le `Caddyfile` commun, et seul le dev y ajoute `watch` (`FRANKENPHP_WORKER_CONFIG`).
    - La règle devient explicite : tout le code de ce step est écrit pour un worker long-vivant. Elle couvre `ResetInterface` sur tout service qui garde un état, l'`EntityManager` remis à zéro après un échec, les connexions Doctrine pingées (`doctrine_ping_connection`), et aucun état dans des propriétés statiques.
    - Deux garde-fous en production :
      - `FRANKENPHP_LOOP_MAX=500` : le worker redémarre après 500 requêtes, en défense en profondeur contre les fuites mémoire et un état résiduel oublié. C'est déjà la valeur par défaut de `symfony/runtime`, on l'écrit pour la rendre explicite ;
      - un test fonctionnel qui rejoue le scénario « deux requêtes, deux acteurs » **dans un vrai worker**, en plus du test dans le kernel de test : FrankenPHP est lancé en CI via `docker compose up`, avec `num 1` dans `FRANKENPHP_WORKER_CONFIG` pour garantir que les deux requêtes HTTP successives passent par le même worker.
    - **Connexions hors bus.** `doctrine_ping_connection` ne protège que le `command.bus`. Sont donc concernées les lectures DBAL, la connexion `rate_limiter` et le PDO des sessions :
      - **délais de session** : `lock_timeout = 2s` et `statement_timeout = 5s` au niveau de la session, posés **là où la connexion naît**. Les options d'un DSN en URL ne conviennent pas : `constructPdoDsn()` de DBAL et `PdoSessionHandler::buildDsnFromUrl()` les ignorent sans erreur.
        - **Connexion `rate_limiter`.** Un middleware de pilote DBAL, `SessionTimeoutsDriverMiddleware` (`Doctrine\DBAL\Driver\Middleware`, tag `doctrine.middleware` avec `connection: rate_limiter`), exécute `SET lock_timeout = '2s'` et `SET statement_timeout = '5s'` juste après `connect()`. Il couvre aussi le store `DoctrineDbalPostgreSqlStore`, qui partage cette connexion. La connexion Doctrine principale n'est pas touchée.
        - **Connexion sessions.** `PdoSessionHandler` reçoit un **DSN PDO natif**, construit à partir des composants de `DATABASE_URL` par une petite fabrique : `pgsql:host=…;port=…;dbname=…;options='-c lock_timeout=2000 -c statement_timeout=5000'`. libpq lit bien `options` dans ce format. On n'utilise ni URL, ni `PGOPTIONS` (qui vaudrait pour tout le processus), ni `ALTER ROLE` (qui toucherait la connexion principale hors transaction).
        - **Effet.** Sur ces connexions en autocommit, un `SET` de session s'applique bien, contrairement à `SET LOCAL`. Le verrou interne des limiteurs (`acquire(true)`, qui donne un `pg_advisory_lock`) et le verrou advisory des sessions ont donc une borne.
        - **Traduction des dépassements.** Elle est faite à la fois dans `SymfonyRateLimiterThrottle` et dans `LoginRateLimiter` : les exceptions DBAL 55P03 et 57014, et `LockAcquiringException` du composant Lock qui peut les envelopper, deviennent `RateLimiterStorageUnavailable`. C'est un échec fermé, audité une seule fois (`throttle.storage_failed`), jamais une erreur 500 non auditée.
        - **Côté sessions.** Un dépassement (contention sur une même session) donne une **503 générique**, journalisée. Il ne crée ni ne régénère de session, et ne retombe jamais sur une session anonyme ensuite écrite.
        - **Tests d'intégration.**
          - `SHOW lock_timeout` vaut `2s` et `SHOW statement_timeout` vaut `5s` sur chacune des deux connexions, et pas sur la connexion principale.
          - Un verrou de limiteur tenu par une autre connexion fait refuser le login en moins de 3 s, avec une seule entrée d'audit.
          - Un verrou advisory de session tenu par une autre connexion donne une 503 en moins de 3 s.
      - **aucun nouvel essai sur les connexions qui portent des verrous** (`rate_limiter` et sessions) : un verrou advisory appartient à la session PostgreSQL, et une reconnexion le perdrait en silence. En cas d'erreur de connexion, on échoue fermé directement, et `FRANKENPHP_LOOP_MAX` renouvelle les connexions. Seules les lectures DBAL sans verrou (`ListAuditEntries`) peuvent retenter une fois. Un test le vérifie : une connexion coupée pendant `ExclusiveSection` donne `Throttled` ou une erreur 503, et le code n'est jamais évalué ;
      - `FRANKENPHP_LOOP_MAX` limite la durée de vie des connexions.
    - **Dimensionnement.** Chaque worker ouvre jusqu'à 3 connexions : Doctrine, `rate_limiter` et sessions. La procédure de production dimensionne `max_connections` de PostgreSQL en conséquence.
    - On ajoute une règle de qualité dans le `CLAUDE.md` de la console : **aucune propriété `static` mutable**, et tout service avec un état implémente `ResetInterface`.

**Retour de l'utilisateur à la présentation de la révision 15** (09/11/2026)

31. **Turbo, avec des Turbo Frames et des placeholders pour charger les données.**
    - **Frames lazy pour les zones lourdes seulement** : les listes (membres, invitations, projets, environnements, utilisateurs et équipes en admin), les jauges de quota et le journal d'audit paginé. La sidebar (`TeamSwitcher`, `NavUser`), les en-têtes et le breadcrumb sont rendus directement par le serveur.
    - **Après une action** : le formulaire est dans une frame ciblée.
      - En cas d'erreur de validation, la frame se re-rend avec un statut 422.
      - En cas de succès, une **réponse Turbo Stream** remplace les frames concernées (la liste, la jauge) et affiche un message, sans recharger la page.
      - Il n'y a pas de temps réel : pas de Mercure.

## Approche recommandée

### Principes transverses

- **Frontières entre contextes.** Les contextes ne s'importent jamais entre eux (`LayerDependencyTest`). Ce qu'ils partagent est dans **`Shared`** :
  - des ports implémentés par un seul contexte ;
  - des messages inter-contextes sous `Shared\Application\Contract\<Contexte>\` : requêtes, commandes, et événements d'intégration publiés sur `event.bus` ;
  - l'enum du catalogue des permissions.

  Le Domain reste pur : pas de Symfony Security, de scheb, de Mailer, ni de Clock. On ajoute à la liste blanche du Domain `Symfony\Component\String`, une fonction pure exigée par les conventions (`u()`).
- **Frontière de cohérence = l'équipe.** Toute commande qui touche aux memberships, aux invitations, aux projets, aux environnements ou aux quotas d'une équipe :
  - commence par charger `Team` avec un **verrou pessimiste** (`SELECT … FOR UPDATE`) via `TeamRepository::lockById()` ;
  - sérialise ainsi les contrôles de quota et les règles de garde de cette équipe : dernier admin, unicité, comptages.

  Quand une commande touche plusieurs équipes, elle verrouille dans un ordre stable (tri par `teamId`).
- **Carte des agrégats.** Chaque élément a une racine désignée :

  | Racine | Contenu |
  |---|---|
  | `Team` | `TeamMembership` |
  | `Project` | `ProjectMembership` et `Environment` (entité interne) |
  | `Invitation` | Agrégat séparé |
  | `PermissionGrant` | Agrégat séparé, en ajout seul |
  | `InstanceSettings` | Singleton |

  Une même transaction modifie parfois plusieurs de ces agrégats. Par exemple, `AcceptInvitation` touche l'invitation, la membership d'équipe, celle du projet et le `PermissionGrant`, et `RemoveTeamMember` retire la membership d'équipe puis celles des projets. Cet écart à la règle « un agrégat par transaction » est **assumé** : tous ces agrégats sont sérialisés par le verrou de `Team`. Il est consigné dans le `CLAUDE.md` de la console.
- **Autres verrous.**
  - **Dernier super admin actif** : `RevokeSuperAdmin` et `DeactivateUser` prennent `pg_advisory_xact_lock` sur une clé constante avant de compter.
  - **Usage unique des codes** : **toute commande qui modifie `SecondFactor`, `BackupCode`, `EmailLoginCode` ou `Credentials`** charge `User` via `UserRepository::lockById()` (`FOR UPDATE`). Cela concerne notamment `VerifyEmailLoginCode`, `IssueEmailLoginCode`, `VerifyTotp`, `UseBackupCode`, `StartTotpEnrollment`, `ConfirmTotp`, `DisableTotp`, `RegenerateBackupCodes`, `ResetSecondFactor` et `ChangePassword`. Un code de l'ancien lot ne peut donc pas être accepté pendant une régénération. Un test de concurrence vérifie qu'un même code de secours envoyé deux fois ne réussit qu'une fois.
  - **Création d'un compte** : `ActivateInvitedAccount` prend `pg_advisory_xact_lock(hashtext(email normalisé))`, car la ligne n'existe pas encore. La contrainte d'unicité sur l'email sert de filet.
- **Mode worker.** Aucun service de domaine ne garde d'état. Tout état de requête vit soit dans un service d'Infrastructure qui implémente `ResetInterface` (tag `kernel.reset`), soit dans les attributs de la `Request`. Un test fonctionnel enchaîne deux requêtes, avec deux acteurs différents, dans le même kernel.
- **Effets après le commit.** Les emails partent sur des **événements de domaine** publiés après le commit, puis sont envoyés en `kernel.terminate`, une fois la réponse partie, par `DeferredMailQueue` (qui implémente `ResetInterface`). On évite ainsi :
  - un lien envoyé alors que le commit a échoué ;
  - une différence de temps de réponse entre « compte existant » et « compte inconnu ».

  Le jeton en clair ne vit qu'en mémoire, dans l'événement. Ces événements ne sont jamais sérialisés, journalisés ni audités, et le transport `event.bus` reste synchrone. Ce point est documenté pour le jour où le bus deviendra asynchrone : à ce moment-là, on passera par un identifiant à usage unique.
- **Codes de réponse.** On renvoie **404** pour toute ressource hors de la portée de l'acteur (il ne doit pas savoir qu'elle existe), et **403** quand il voit l'objet mais n'a pas la permission pour l'action. Les deux sont audités.
- **Autorisation des objets enfants.** Un handler charge toujours l'objet (invitation, membership, environnement…), en déduit son équipe et son projet *réels*, puis vérifie la permission sur ce propriétaire. Il ne se fie jamais à l'id de l'URL. Il vérifie aussi `projectId ∈ teamId`.
- **Formulaires.** Ils alimentent des DTO de commande, jamais des entités.
- **CSRF sur toute requête qui modifie l'état.**
  - Les formulaires passent par le composant Form.
  - **Les boutons seuls sont eux aussi des formulaires, sans champ** : renvoyer ou révoquer une invitation, Re-sync, réinitialiser le 2FA, désactiver un compte, accorder ou retirer le super admin… Ils utilisent `ActionButtonType`, avec un `csrf_token_id` propre à chaque action. **Toute requête qui modifie l'état passe donc par le composant Form avec CSRF.** Les actions de l'espace authentifié passent aussi par `ActionResponder::handle()`.
  - **Pages d'authentification**, la seule exception à `ActionResponder`. La liste est exacte et fermée : connexion, second facteur, `/reauthenticate`, `/password/forgot`, `/password/reset/new`, `/invitations/pending` (activation avec choix du mot de passe) et `POST /invitations/accept`. Leur CSRF est explicite :
    - **connexion et logout** : `form_login` avec `enable_csrf: true`, et logout en POST avec CSRF ;
    - **second facteur** : scheb `two_factor` avec **`enable_csrf: true`** et un `csrf_token_id` dédié ;
    - **les cinq autres** : formulaires Form avec CSRF, chacun avec son propre `csrf_token_id`.

    Un jeton invalide sur l'une de ces pages donne une **403**, auditée **une fois** en `csrf.rejected` (`denied`) par le même collaborateur que celui d'`ActionResponder` (`CsrfRejection`, voir plus bas). Il y a pourtant deux chemins différents :
    - **Connexion et second facteur.** Ici, un jeton invalide lève `InvalidCsrfTokenException`, qui est une `AuthenticationException`. L'authenticator l'envoie donc à `onAuthenticationFailure`, avec par défaut une 302 et un `LoginFailureEvent`. Pour obtenir la 403, un **`CsrfAwareFailureHandler`** est posé en `failure_handler` sur `form_login` **et** sur `two_factor` (scheb).
      - S'il reçoit une `InvalidCsrfTokenException`, il délègue à `CsrfRejection` : 403 et `csrf.rejected`.
      - Sinon, il délègue au handler par défaut.
      - Le subscriber d'audit d'authentification **ignore** les `LoginFailureEvent` dont l'exception est `InvalidCsrfTokenException`. Une tentative produit donc une seule entrée. Le code du second facteur n'est jamais évalué, puisque le badge CSRF est vérifié avant.
    - **Logout.** C'est la huitième route. Un jeton invalide lève `LogoutException`. Le listener `kernel.exception` la reconnaît et la délègue à `CsrfRejection`, qui rend la 403 et écrit `csrf.rejected`. Elle n'est jamais auditée comme un `denied` générique.
    - **Les cinq autres pages** (formulaires Form) appellent directement `CsrfRejection`.

    Le test « POST sans jeton → 403, une seule entrée `csrf.rejected` » couvre ces **huit** routes (les sept routes d'authentification et le logout), en plus des actions de l'espace authentifié. Pour la connexion et le second facteur, il vérifie qu'aucune entrée « échec de connexion » n'est écrite en plus.
  - **Aucun `GET` ne modifie l'état.**

  Ce contrôle s'ajoute à `SameSite=Strict`, qui ne protège pas d'un sous-domaine voisin. Un test fonctionnel couvre chaque action POST : sans jeton, 403.
- **Après le `dispatch`, l'UI relit ses données par une requête**, sans réutiliser les entités chargées avant. Un `clear()` après l'échec d'une cascade peut en effet les avoir détachées. Un test fonctionnel couvre ce cas : la cascade échoue, puis la page s'affiche correctement.

### Shared — socle commun (commit 1)

**Agrégats et événements**

- L'interface `Shared\Domain\Model\RecordsEvents` et le trait `EventRecording` (`recordThat`, `releaseEvents`) remplacent l'héritage d'une classe abstraite.
- `DomainEventCollector`, en Infrastructure, est un listener Doctrine `onFlush` qui implémente `ResetInterface`. Il parcourt **toute l'identity map** et les insertions programmées. Les événements d'une racine non modifiée, dont seuls les enfants changent, ne sont donc pas perdus, et un test le vérifie. Il est vidé par `PublishDomainEventsMiddleware` en cas d'exception.

**Middlewares du `command.bus`**, dans cet ordre explicite (`messenger.yaml`, avec un commentaire qui le justifie) :

| Ordre | Middleware | Rôle |
|---|---|---|
| 1 | `PublishDomainEventsMiddleware` | Le plus externe. Quand la chaîne réussit, donc après le commit, il publie les événements collectés sur `event.bus`. Si un handler d'événement échoue, la commande **n'est pas** requalifiée : l'échec est journalisé (`error`) et audité sous sa propre action `event.handler.failed`, avec l'événement et le handler. Il n'est pas relancé, car l'effet est déjà validé, et chaque réaction est conçue pour être rejouable. |
| 2 | `AuditFailureMiddleware` | Attrape l'exception **après le rollback** et écrit l'entrée `failure` ou `denied` sur la connexion revenue à un état propre. Il déroule ensuite `HandlerFailedException` et relance l'exception métier **enveloppée dans `AlreadyAudited`**, en y joignant l'`AuditAction` de la commande. La portée est résolue **avant** tout nettoyage. |
| 2 bis | `ResetUnitOfWorkOnFailureMiddleware` | Juste à l'intérieur de l'audit d'échec, et à l'extérieur de `doctrine_transaction`. Sur exception, il remet l'unité de travail à zéro, puis relance l'exception (voir plus bas). |
| 3 | `doctrine_ping_connection`, `doctrine_close_connection`, `doctrine_open_transaction_logger`, `doctrine_transaction` | Middlewares Doctrine existants, conservés. |
| 3 bis | `LockTimeoutMiddleware` | Placé **juste à l'intérieur** de `doctrine_transaction`, donc après le `BEGIN`. Il exécute `SET LOCAL lock_timeout = '5s'`, qui ne vaut que pour la transaction de la commande. Un `FOR UPDATE` (`User`, `Team`) ou un `pg_advisory_xact_lock` qui attend plus de 5 s échoue avec SQLSTATE 55P03, audité une seule fois en `failure` / `technical`. Un test d'intégration le vérifie : une ligne `User` verrouillée par une autre connexion fait échouer la commande en 5 s environ. |
| 4 | `AuditSuccessMiddleware` | Le plus interne. Écrit l'entrée `success` **dans la transaction**, de façon atomique avec l'effet. |

**`query.bus`** : un seul middleware maison, **`AuditDeniedQueryMiddleware`**. Il audite `PermissionDenied` et `ResourceNotFound` levés par un handler de requête (`denied`). Il déroule d'abord lui-même `HandlerFailedException`, puis relance l'exception métier enveloppée dans `AlreadyAudited`, un objet immuable dont `cause()` rend l'exception métier. Les lectures réussies ne sont pas auditées.

**Bus d'événements, sans transaction.** On retire `doctrine_transaction` de `event.bus` dans `messenger.yaml`, en commentant pourquoi : la transaction appartient à la commande seule, et il n'y a qu'un niveau.

**Aucun handler d'événement ne modifie l'état persistant.** Il fait l'une de ces trois choses :
- envoyer une commande sur `command.bus` ;
- mettre un email dans la file différée ;
- republier un événement d'intégration.

Chaque réaction qui modifie l'état a ainsi son propre commit, avec ses verrous, son audit et sa publication, et les emails ne partent que pour des effets réellement commités.

**Mémoire remise à zéro après un échec.** Le rollback annule la base, mais pas l'`EntityManager`. Cette remise à zéro a son **propre middleware**, `ResetUnitOfWorkOnFailureMiddleware` : elle se fait au niveau du bus et pas dans chaque handler. L'ordre compte :

1. **Résolution de la portée d'audit.** Comme `AuditFailureMiddleware` est plus externe, il ne voit l'exception qu'après le nettoyage. Pour que l'audit connaisse quand même la cible, ce middleware résout la portée via `AuditScopeResolver` **avant de nettoyer**, et la joint à l'exception (`AuditScopeStamp`). L'audit d'échec lit cette portée. Si elle est absente, il utilise `Scope::none()`.
2. **Purge des événements.** Le middleware prend la liste des entités gérées, puis purge leurs événements non publiés. C'est une ceinture de sécurité, documentée comme telle : une entité détachée n'est de toute façon plus vue par le collecteur.
3. **Vidage.** Il appelle `EntityManager::clear()`, ou `ManagerRegistry::resetManager()` si l'EM est fermé. Les services qui lisent l'ORM, comme `AuditScopeResolver` et les repositories, passent par `ManagerRegistry` et non par un EM injecté une fois pour toutes.

Les mutations et les événements d'une commande annulée ne peuvent donc pas ressortir au `flush` suivant de la même requête. Un test d'intégration vérifie le scénario suivant :
- la commande A modifie une entité, puis échoue ;
- la commande B s'exécute ensuite dans la même requête ;
- rien de A n'est persisté ni publié ;
- la portée de l'entrée `failure` de A est correcte ;
- l'acteur et les permissions de B sont recalculés depuis la base.

**Réentrance.** `PublishDomainEventsMiddleware` **vide le collecteur avant de publier** (`releaseEvents` d'abord, `dispatch` ensuite). Une commande imbriquée ne republie donc jamais les événements de la commande externe. Un test d'imbrication vérifie qu'aucun événement n'est perdu ni publié deux fois.

**Échec d'une réaction : trois entrées, pas une.** Quand une commande imbriquée échoue, on écrit :

| Entrée | Écrite par |
|---|---|
| `success` | la commande externe |
| `failure` | la commande imbriquée, via son propre `AuditFailureMiddleware`, hors de toute transaction |
| `event.handler.failed` | `PublishDomainEventsMiddleware`, en référençant l'action de la commande échouée et le request id |

Un test d'intégration vérifie ces trois entrées, et qu'aucun email de la commande échouée ne part.

**Contenu des logs et de l'audit en cas d'échec.** Pour `event.handler.failed`, l'audit et le contexte du log `error` contiennent **uniquement** :
- le FQCN de l'événement ;
- le FQCN du handler **le plus interne** (on déroule les `HandlerFailedException` imbriquées via `UnwrapsHandlerFailure`, pour nommer par exemple le handler d'Organization plutôt que le traducteur) ;
- l'`AuditAction` de la commande échouée (le request id est déjà dans `RequestContext`) ;
- la classe de l'exception.

Ils ne contiennent jamais l'objet événement, l'enveloppe ou le message de l'exception. Un test vérifie qu'un `InvitationSender` en échec ne laisse le jeton ni dans `audit_log`, ni dans les logs.

**Mailer sans Messenger.** On pose `framework.mailer.message_bus: false`. Sinon, les emails passeraient par `command.bus`, avec ses middlewares d'audit.

Le refus métier passe par une exception unique, `Shared\Application\Authorization\PermissionDenied` (portée visible, donc 403), ou par `ResourceNotFound` (hors portée, donc 404). `AuditFailureMiddleware` (n° 2) l'audite une seule fois, et l'UI la traduit en 403 ou 404 **sans auditer une seconde fois**. Un test vérifie qu'un refus produit exactement une entrée.

**Ports**

- **Identifiants.** Un value object par agrégat (`UserId`, `TeamId`…), sur `Uuid` v7, avec un type Doctrine `uuid` par id. C'est une exception tolérée à la règle « pas d'héritage », parce que le framework l'impose. Les ids sont générés côté UI et passés dans les commandes, si bien que l'audit connaît toujours la cible.
- **Horloge.** `Psr\Clock\ClockInterface` en Application (via `symfony/clock`). Le Domain reçoit des `DateTimeImmutable`.
- **`CurrentActor`** (identité) et **`RequestContext`** (IP, user-agent tronqué à 512, request id) sont deux ports distincts.
  - `Actor::user(id)`, `Actor::cli()`, `Actor::system()` et `Actor::anonymous()` évitent un id `null`.
  - Le statut de super admin a une **source unique** : le `User` du Domain (`isSuperAdmin`), traduit en `ROLE_SUPER_ADMIN` dans `SecurityUser`. Les voters comme les handlers lisent l'acteur résolu.
  - Les adaptateurs s'appuient sur `RequestStack` et `Security`, et implémentent `ResetInterface`.
  - Le request id est **toujours généré par le serveur** et renvoyé dans l'en-tête `X-Request-Id`. Un `X-Request-Id` entrant est ignoré.
- **IP de confiance.** On configure `framework.trusted_proxies` et `trusted_headers` via `SYMFONY_TRUSTED_PROXIES`, vide par défaut (exposition directe, `X-Forwarded-For` ignoré). La procédure derrière un reverse proxy est documentée.
- **`SecretBox`** chiffre en AES-256-GCM.
  - Format stocké : `v1:<kid>:` + base64(nonce ‖ tag ‖ ciphertext).
  - L'AAD vaut nom du champ + id du propriétaire. Un secret copié d'une ligne vers une autre ne se déchiffre donc pas.
  - La clé est lue dans `APP_ENCRYPTION_KEYS` (ou `APP_ENCRYPTION_KEYS_FILE`), une liste `kid=base64`. La première clé chiffre, toutes déchiffrent : c'est ce qui permet la rotation.
  - **Échec fermé** : au démarrage, une clé absente ou différente de 32 octets lève une erreur hors des environnements dev et test.
- **Jetons et codes.** Une stratégie de format par usage, derrière le même `TokenHasher`. Ce dernier calcule un **HMAC-SHA-256 avec une clé serveur** (`APP_HASH_PEPPER`, en échec fermé comme la clé de chiffrement). Une fuite de la base ne suffit donc pas pour attaquer les codes hors ligne.
  - Le pepper suit le même format `kid=base64` que `APP_ENCRYPTION_KEYS`. Le hash stocké porte son `kid`, et la vérification essaie toutes les clés : c'est ce qui permet la rotation.
- **`APP_SECRET` en échec fermé.** Il signe le cookie d'appareil de confiance de scheb, qui permet de sauter le 2FA pendant 30 jours. Il est donc traité comme une clé :
  - vide dans `.env`, avec une valeur seulement dans `.env.dev` et `.env.test` ;
  - absent ou plus court que 32 octets hors dev et test : refus au démarrage, avec un test ;
  - la rotation est documentée : changer `APP_SECRET` invalide tous les appareils de confiance, et c'est voulu.

  | Usage | Format |
  |---|---|
  | Liens (invitation, réinitialisation) | `UrlToken`, 256 bits en base64url |
  | Code email | `NumericCode`, 6 chiffres via `random_int` |
  | Code de secours | `BackupCodeFormat`, 10 caractères dans un alphabet sans ambiguïté, groupés `xxxxx-xxxxx` |

  La comparaison se fait en temps constant pour les codes.
- **Audit.** `Shared\Application\Audit\AuditTrail` est le port, avec `record(AuditEntry)`. `AuditEntry` est composée de `Actor`, `AuditAction`, `Target`, `Scope` (équipe et projet), `Outcome` et `RequestContext`.
  - Son contexte est **sûr par construction** : une liste blanche de clés par action, des valeurs scalaires typées, une taille bornée à 4 Ko.
  - Les commandes déclarent leur action via `AuditableCommand`.
  - **`AuditScopeResolver` est un port de `Shared\Application\Audit`**, déclaré avec `#[AutoconfigureTag]` et injecté par `#[AutowireIterator]`. Chaque contexte en fournit les implémentations pour ses propres cibles, dans sa propre Infrastructure (par exemple Organization pour `Invitation`, `Project` et `Environment`). Audit n'importe donc jamais un autre contexte.
  - Le resolver passe par l'ORM (identity map). Il voit ainsi les entités pas encore flushées, comme une cible en cours de création.
  - Pour une cible inconnue, par exemple après le rollback d'une création, il renvoie `Scope::none()` sans échouer. Un test couvre le chemin `failure` d'une création.
  - La commande ne transporte donc aucune portée fournie par le client.
  - **Commandes auto-auditées.** `VerifyEmailLoginCode`, `VerifyTotp`, `UseBackupCode` et **`ConfirmTotp`** implémentent `SelfAuditedCommand`. **Seul `AuditSuccessMiddleware` les ignore.** Une exception technique (verrou en timeout, base indisponible) est donc toujours auditée en `failure` par `AuditFailureMiddleware`, avec la raison `technical`, et un test le vérifie. Sur le chemin normal, leur handler écrit une seule entrée, dont le résultat est lu dans `CodeVerificationAttempt` : `Accepted` donne `success`, `Rejected`, `Exhausted` ou `Expired` donnent `failure`, et `Throttled` donne `denied` (raison `throttled`). C'est la seule table de correspondance entre résultat et audit. Le subscriber d'authentification n'écrit pas d'entrée « 2FA » en double. Un test vérifie qu'un mauvais code produit une seule entrée `failure`.
- **Permissions.** L'enum `Shared\Domain\Authorization\Permission` est le catalogue publié en §7bis (`account.login`, `instance.*`, `team.*`, `host.*`, `project.*`, `finding.*`). Il est assumé que chaque nouveau contexte fera évoluer ce catalogue : il est publié dans le cadrage.
- **Slug.** Le port `SlugGenerator`, en Application, est implémenté par `SluggerInterface`. Il prend en charge le suffixe d'unicité. Les agrégats reçoivent le slug déjà calculé.
- **En-têtes de sécurité.** Un subscriber `SecurityHeadersSubscriber` pose :
  - une CSP stricte (`default-src 'self'`, `frame-ancestors 'none'`, `form-action 'self'`, `base-uri 'none'`) ;
  - HSTS, sauf en dev ;
  - `X-Content-Type-Options: nosniff` ;
  - `Referrer-Policy: no-referrer`.

  Il est compatible avec Vite en dev, grâce à une CSP propre à l'environnement dev.

### Audit (commit 1)

**Rôles et table**

- **Rôles.** Le script `.docker/database/roles.sh` crée deux rôles. Il est **idempotent** (`CREATE ROLE … IF NOT EXISTS` via `DO`, puis mise à jour du mot de passe) :
  - `depverify_owner`, le propriétaire des schémas ;
  - `depverify_app`, le rôle runtime, `NOSUPERUSER NOCREATEDB NOCREATEROLE`.
- **Exécution du script.** Il est monté dans `/docker-entrypoint-initdb.d/` pour un volume neuf, et lancé par `make db-roles` pour un volume existant (la commande est documentée).
- **Identifiants dans `compose.yaml`.** Le service `php` reçoit `DATABASE_URL` construite avec `depverify_app` et un mot de passe dédié, **à la place** de l'actuelle URL du superutilisateur `POSTGRES_USER`. Une vraie variable d'environnement passe devant `.env`.
- **Identifiants du propriétaire.** `DATABASE_MIGRATIONS_URL` n'est **jamais** visible du worker web.
  - Elle n'apparaît dans **aucun** fichier `.env*` lu par `symfony/runtime`.
  - Elle est définie dans `.docker/database/owner.env`, ignoré par git, avec un modèle versionné `owner.env.dist`. Ce fichier n'est **pas monté** dans le service `php`.
  - Le `Makefile` le charge dans l'environnement de `make` côté hôte. Il le passe ensuite **sans valeur sur la ligne de commande**, avec `docker compose exec -e DATABASE_MIGRATIONS_URL`, ce qui hérite de l'environnement : le secret n'apparaît pas dans `ps`.
  - Cette injection est limitée à `db-migrate`, `db-diff` et `audit-partitions`. **Pas à `super-admin`**, qui écrit avec le rôle runtime.
  - Dans `doctrine.yaml`, la connexion `owner` utilise `%env(default::DATABASE_MIGRATIONS_URL)%`, pour que le conteneur compile sans la variable. Elle lève une exception si `PHP_SAPI !== 'cli'`.
  - Un test fonctionnel vérifie que, dans le kernel web, `getenv()`, `$_SERVER` et `$_ENV` ne contiennent pas `DATABASE_MIGRATIONS_URL`.
- **Superutilisateur `POSTGRES_USER`.** Il ne sert plus qu'à l'initialisation. La procédure de production impose de changer son mot de passe et de ne pas l'exposer sur le réseau.
- **Schéma dédié `audit`.** `audit.audit_log` vit dans un schéma à part, propriété de `depverify_owner`.
  - `depverify_app` reçoit seulement `USAGE` sur ce schéma.
  - Les privilèges par défaut du schéma (`ALTER DEFAULT PRIVILEGES IN SCHEMA audit`) se limitent à `INSERT, SELECT`.
  - `maintain-partitions` réapplique explicitement `REVOKE ALL` puis `GRANT INSERT, SELECT` sur chaque partition qu'il crée.
  - Les tables applicatives restent dans `public`, avec leurs propres `GRANT`. Cela comprend la table d'état des limiteurs, `rate_limiter_state`, créée par migration.
- **Table `audit.audit_log`.** Créée par une migration en SQL brut, partitionnée par `RANGE (occurred_at)` mensuel :
  - clé primaire `(id, occurred_at)` ;
  - index sur `(team_id, occurred_at)`, `(actor_id, occurred_at)` et `(action, occurred_at)` ;
  - une partition `DEFAULT`, plus les 12 prochains mois ;
  - un trigger de ligne `BEFORE UPDATE OR DELETE` et un trigger d'instruction `BEFORE TRUNCATE`, qui lèvent tous deux une exception.
- **Tests d'intégration.**
  - L'application s'exécute avec `current_user = 'depverify_app'` et `NOT rolsuper`.
  - Sur une partition créée **par `maintain-partitions` après la migration**, comme sur `DEFAULT`, les opérations `UPDATE`, `DELETE` et `TRUNCATE` directes par le rôle runtime échouent.

**Écriture et maintenance**

- `Audit\Infrastructure\DbalAuditTrail` implémente `AuditTrail` en ajout seul, par un `INSERT` DBAL.
- `app:audit:maintain-partitions` tourne sous le rôle propriétaire. Il est idempotent :
  1. il crée les 12 prochains mois ;
  2. s'il trouve des lignes d'un mois dans la partition `DEFAULT`, il les déplace **dans une seule transaction, sous le rôle propriétaire** :
     1. `LOCK TABLE audit.audit_log IN ACCESS EXCLUSIVE MODE` ;
     2. `DETACH PARTITION` de la partition `DEFAULT` ;
     3. création de la partition du mois ;
     4. `INSERT INTO audit.audit_log SELECT … FROM` l'ancienne `DEFAULT` pour ce mois ;
     5. `ALTER TABLE` sur l'ancienne `DEFAULT` : `DISABLE TRIGGER USER`, `DELETE` des lignes déplacées, puis `ENABLE TRIGGER USER` ;
     6. `ATTACH` de nouveau en `DEFAULT`, puis `REVOKE` et `GRANT` sur les partitions.

     Le verrou exclusif empêche toute écriture pendant l'opération, et les triggers sont réactivés avant le commit. Un test vérifie que `maintain-partitions` réussit avec des lignes dans `DEFAULT` et que, juste après, `UPDATE`, `DELETE` et `TRUNCATE` restent refusés ;
  3. il détache puis supprime (`DROP`) les partitions entièrement plus anciennes que `AUDIT_RETENTION_DAYS`.

**Consultation et refus**

- La requête `ListAuditEntries` lit en DBAL, avec des filtres et une pagination par curseur `(occurred_at, id)`.
- Les écrans : l'audit global exige `instance.audit.view`, l'audit d'équipe exige `team.audit.view` sur la `TeamId`.
- Le listener `kernel.exception` n'audite qu'un refus **qui n'est pas enveloppé dans `AlreadyAudited`** : refus du firewall (`access_control`) ou d'un voter appelé dans un contrôleur. Le middleware qui audite un refus l'enveloppe dans `AlreadyAudited`, sur le `command.bus` (`AuditFailureMiddleware`) comme sur le `query.bus` (`AuditDeniedQueryMiddleware`). Aucun bus ne retire cette enveloppe, car `UnwrapsHandlerFailure` ne déroule que `HandlerFailedException`. Le listener lit `cause()`. Il y a donc exactement une entrée par refus, quelle que soit la source. Un test le vérifie pour chaque source.
- Le volume d'audit est un risque connu : un attaquant peut gonfler la table en multipliant les échecs. Il est documenté, et la surveillance de sa taille est un non-objectif de ce step.

### Identity (commit 2)

**Domaine (`Identity\Domain\Model`)**

`User` est un agrégat composé d'embeddables, dont aucune méthode publique ne renvoie `null` :

| Embeddable | Contenu |
|---|---|
| `UserId`, `EmailAddress` | Email normalisé en minuscules via `u()`, 254 caractères au plus, unique. |
| `Credentials` | `none` ou `password(hash)`, avec `hasPassword()`. |
| `SecondFactor` | Pattern **State** : `NotConfigured`, `PendingTotp(secretChiffré)` ou `ActiveTotp(secretChiffré, since)`. Un secret non confirmé est simplement remplacé. **Chaque état implémente toutes les opérations** (`startTotpEnrollment`, `confirmTotp`, `verifyTotp`, `disableTotp`, `reset`). Une transition invalide, par exemple `verifyTotp` sur `NotConfigured` ou `confirmTotp` sur `ActiveTotp`, lève l'exception de domaine `InvalidSecondFactorTransition`, de la famille `BusinessRuleViolated`, auditée en `denied` / `rule:invalid_second_factor_transition`. Elle reste distincte d'un mauvais code, qui renvoie `Rejected`. Les exceptions idempotentes sont listées sous la table. |
| `SessionVersions` | `authVersion` et `trustedDeviceVersion`, avec `revokeAll()`. |
| `AccountStatus` | `active` ou `disabled(since)`. |
| `Privileges` | `isSuperAdmin` et les permissions d'instance (`account.login`). |

**Exceptions idempotentes de `SecondFactor`** :
- `reset` est total et sans effet sur `NotConfigured` : c'est le geste de secours du super admin ;
- `disableTotp` sur `PendingTotp` abandonne l'enrôlement ;
- `startTotpEnrollment` sur `PendingTotp` remplace le secret.

Un test couvre chaque couple état/opération, en distinguant les cas « sans effet » et « exception ».

**Persistance des états.** Un embeddable Doctrine n'a qu'une seule forme. `Credentials`, `SecondFactor` et `AccountStatus` stockent donc une colonne `kind` et leurs champs, qui ne sont nullables qu'en base. Une factory reconstruit l'objet d'état (`state(): SecondFactorState`), et l'invariant « champs requis selon `kind` » est contrôlé à la reconstruction. Un test aller-retour couvre chaque état.

`ActiveTotp` porte **`lastAcceptedStep`**. Un code TOTP dont le pas de temps est inférieur ou égal à `lastAcceptedStep` est refusé : c'est la protection contre le rejeu.

**Règle générale des 4 attributs.** Les racines et les entités persistées regroupent leurs champs en embeddables quand c'est possible :
- `Invitation` : `InvitationTarget` (type, id, rôle) et `IssuedToken` (hash, date d'émission) ;
- `User` : les embeddables listés plus haut.

Sinon, l'écart est assumé et consigné dans le `CLAUDE.md` de la console. Les écarts connus sont `User` (collections et trait d'événements), `TeamQuotas` (9 champs), `Team`, `Project` et `EmailLoginCode`, comme pour le type `Uuid`.

**Entités de l'agrégat `User`**, modifiées uniquement par ses méthodes et chargées à la demande :

- **`BackupCode`** : hash et `usedAt`. Il y en a 10 au maximum, et en régénérer remplace tout le lot.
- **`EmailLoginCode`** : hash, `expiresAt` (+10 min), `attempts`, `consumedAt` et `consumedByAttemptId`, `invalidatedAt`.
  - Un seul code est actif à la fois, garanti à la fois par l'agrégat et par un index unique partiel `WHERE consumed_at IS NULL AND invalidated_at IS NULL`.
  - `issueEmailLoginCode` invalide d'abord le code actif, même s'il est expiré.
  - `verify(code, attemptId, now)` renvoie `Accepted`, `Rejected`, `Exhausted` ou `Expired`, **sans lever d'exception**. Le résultat `Throttled` ne vient pas de l'agrégat mais du limiteur (voir plus bas). Il fait partie des résultats possibles de `CodeVerificationAttempt`. La méthode `verify` vérifie le code et incrémente elle-même le compteur. Elle modifie donc l'état et renvoie un résultat : cet écart à la séparation commande/requête est assumé et documenté.

**Hors de l'agrégat `User`** : `CodeVerificationAttempt` (`attemptId`, `userId`, `kind` email/totp/backup, `outcome`, `createdAt`) est un **enregistrement technique séparé**, sans invariant métier. C'est le registre des essais, écrit dans la même transaction que l'incrément, et la source de `GetCodeVerificationOutcome` et du résultat d'audit. Ce n'est pas l'audit : le handler de vérification supprime au passage les essais de plus d'une heure du même utilisateur.

**Agrégat séparé**

- **`PasswordResetRequest`** : hash du jeton, `expiresAt` (+30 min) et `consumedAt`. En émettre une nouvelle invalide les précédentes.

**Méthodes métier**

- **Règle : aucun handler ne modifie un état sans passer par une méthode du Domain.** Il n'y a pas de setter public.
- **Constructeurs nommés** : `User::createSuperAdmin(id, email, hash, now)` et `User::activateFromInvitation(id, email, hash, now)`. Un compte « notification seule » existant est complété par `completeActivation(hash, now)`.
- **Second facteur** :
  - `issueEmailLoginCode(hash, now)`, `verifyEmailLoginCode(code, attemptId, now)` ;
  - `startTotpEnrollment(encryptedSecret)`, `confirmTotp(step, attemptId, backupCodeHashes, now)`, `verifyTotp(step, attemptId, now)`. Ces deux dernières portent la règle de `lastAcceptedStep`. `confirmTotp` est un geste distinct de `verifyTotp` : il n'est valide que sur `PendingTotp`, et il renvoie le même résultat que les autres vérifications (`Accepted`, `Rejected`…). Sur `Accepted` seulement, il passe en `ActiveTotp` et enregistre les hashes des codes de secours ;
  - `useBackupCode(code, attemptId, now)`, `regenerateBackupCodes(hashes)`, `disableTotp()`, `resetSecondFactor()`.
- **Compte** : `changePassword(hash)`, `deactivate(now)`, `reactivate()`, `grantSuperAdmin()`, `revokeSuperAdmin()`.
- `deactivate`, le retrait du super admin et toute modification des identifiants (mot de passe, TOTP, codes de secours) appellent `SessionVersions::revokeAll()`.
- Ces méthodes enregistrent les événements `PasswordChanged`, `TotpEnabled`, `TotpDisabled`, `BackupCodesRegenerated`, `SecondFactorReset`, `SuperAdminGranted`, `SuperAdminRevoked`, `UserDeactivated`, `UserReactivated` et **`SecondFactorThrottled`**. Ce dernier est enregistré par `User::noteSecondFactorThrottled(until, now)`, une méthode appelée par le handler de vérification sous le verrou `User` au premier blocage de la fenêtre de 24 h. C'est un fait de sécurité du compte (« second facteur bloqué jusqu'à… »), publié après le commit, qui déclenche `SecurityAlertSender`.
- **Événements d'intégration.** Un traducteur nommé, `PublishAccountIntegrationEvents`, est un handler d'Identity sur `event.bus`. Il republie les faits internes `UserDeactivated` et `UserReactivated` sous des noms distincts du langage publié : `Shared\Application\Contract\Identity\AccountDeactivated` et `AccountReactivated`, qui ne portent que l'id du compte. Organization ne consomme que ces derniers.

**Application**

- **Commandes**, toutes auditables :
  - comptes : `CreateSuperAdmin`, `ActivateInvitedAccount` ;
  - mot de passe : `ChangePassword`, `RequestPasswordReset`, `ResetPassword` ;
  - code email : `IssueEmailLoginCode`, `VerifyEmailLoginCode(userId, code, attemptId)` ;
  - TOTP et codes de secours : `StartTotpEnrollment`, `ConfirmTotp`, `VerifyTotp(userId, code, attemptId)`, `DisableTotp`, `RegenerateBackupCodes`, `UseBackupCode(userId, code, attemptId)`. Les trois facteurs suivent le même algorithme. Il est écrit **une seule fois**, dans le service d'Application `SecondFactorAttempt`, qui compose une Strategy `CodeCheck` par geste (`TotpCheck`, `TotpEnrollmentCheck` pour `ConfirmTotp`, `EmailCodeCheck`, `BackupCodeCheck`).
    - Chaque Strategy **ne fait qu'appeler la méthode de l'agrégat** (`User::verifyTotp`, `verifyEmailLoginCode`, `useBackupCode`). Elle ne lit aucun hash et ne compare rien elle-même.
    - Les handlers se contentent d'assembler `SecondFactorAttempt` et la Strategy.
    - **Ordre des verrous** : d'abord le verrou `User` (`FOR UPDATE`, transaction de la commande), puis la section exclusive sur la clé IP. Le port **`Shared\Application\Security\ExclusiveSection::run(ThrottleSubject, callable)`** garantit que le verrou est libéré même si une exception est levée.
    - L'adaptateur `LockExclusiveSection`, en Infrastructure, s'appuie sur `LockFactory`, avec un verrou advisory sur la connexion `rate_limiter`, hors de la transaction. Sa clé a un espace de nommage distinct de celui des limiteurs (`2fa-ip:` + HMAC), pour éviter toute collision. L'acquisition a un **délai borné de 2 s**. `Lock::acquire(true)` attend sans limite, donc on ne l'utilise pas. L'adaptateur boucle sur `acquire(false)` avec un court backoff (50 ms, puis davantage), jusqu'à une échéance. Cet adaptateur d'Infrastructure dépend de `Symfony\Component\Clock\ClockInterface` et utilise son `sleep()`, si bien que l'horloge et l'attente réelle restent cohérentes. Le test en moins de 3 s tourne sur l'horloge réelle.
      - **Délai dépassé.** L'utilisateur reçoit le résultat `Throttled`. L'audit, lui, note la raison **`lock_contention`**, distincte de `throttled` : un embouteillage n'est pas un abus.
      - **Libération.** Le verrou est rendu dans un `finally`. Dans une section exclusive, on ne retente **jamais** après une reconnexion : on échoue fermé directement, car le registre de `PostgreSqlStore`, indexé par connexion, serait faussé. La règle « aucune propriété `static` mutable » ne vaut que pour le code du projet.
      - **Test.** Un premier processus tient la section : le second obtient `Throttled` en moins de 3 s, avec la raison `lock_contention`.

      L'Application n'importe donc jamais `Symfony\Component\Lock`.

    La séquence :
    1. `AttemptThrottle::peek()` sur les clés du compte et de l'IP. Si une fenêtre est épuisée, le **résultat** est `Throttled` et le code n'est pas vérifié ;
    2. vérification du code par la Strategy ;
    3. si le code est `Rejected`, `consume(1)` sur les fenêtres de 15 min et de 24 h ;
    4. écriture du registre des essais (`CodeVerificationAttempt`, résultat compris) et d'**une seule** entrée d'audit : `success`, `failure` ou `denied` / `throttled`.

    **Pour ces trois commandes auto-auditées, `Throttled` est un résultat, jamais une exception.** Il est donc lisible par `GetCodeVerificationOutcome`, et l'adaptateur scheb annule le jeton 2FA quand il le reçoit. L'exception `Throttled` est réservée aux commandes ordinaires (voir « Quand une commande est limitée »).

    On compte des **échecs**, conformément à la décision 6. Le verrou `User` rend la séquence atomique pour un compte, et la section exclusive sur la clé IP la rend atomique entre comptes. Les transactions de commande fixent un `lock_timeout` PostgreSQL de 5 s, posé par `LockTimeoutMiddleware` juste après le `BEGIN` (voir le tableau des middlewares). Un verrou `User` qui n'est pas obtenu à temps échoue donc fermé, l'échec est audité `failure` / `technical`, et aucun worker n'attend indéfiniment. L'adaptateur scheb ne fait que traduire le résultat. Pour la ré-authentification, le contrôleur de `/reauthenticate` envoie la même commande. Un test unitaire couvre `SecondFactorAttempt` avec chaque Strategy ;
  - administration : `ResetSecondFactor`, `DeactivateUser`, `ReactivateUser`, `GrantSuperAdmin`, `RevokeSuperAdmin`.
- Les vérifications de code **ne lèvent jamais d'exception** pour un mauvais code. L'incrément est donc bien committé, et l'adaptateur lit ensuite le résultat avec la requête `GetCodeVerificationOutcome(attemptId)`.
- **`ActivateInvitedAccount(token, password)`** :
  - résout l'invitation par `FindPendingInvitation` et **en tire l'email** ;
  - refuse si l'invitation n'est pas en attente, ou si le compte a déjà un mot de passe ou `account.login` ;
  - crée le compte, ou complète un compte « notification seule », en définissant le mot de passe et en accordant `account.login` ;
  - prend un verrou advisory sur l'email normalisé, ce qui protège contre une double activation simultanée (un test le vérifie).
- **Requêtes** : `GetUserProfile`, `ListUsers`, et le contrat `FindUsersByIds`.
- **Ports fins** : `LoginCodeSender`, `PasswordResetSender`, `SecurityAlertSender`, `PasswordHasher` et `UserRepository`.

**Infrastructure : sécurité**

- **`SecurityUser`** est un instantané qui implémente `UserInterface`, `PasswordAuthenticatedUserInterface`, `TwoFactorInterface` (TOTP, codes de secours, appareil de confiance) et `EquatableInterface`.
  - L'égalité porte sur l'id, `authVersion` et `isSuperAdmin`. C'est l'invalidation native de Symfony : un changement de version déconnecte toutes les sessions.
  - **`__serialize()` ne garde que l'id, l'email, `authVersion` et `isSuperAdmin`.** Le hash du mot de passe et le secret TOTP n'entrent jamais dans la session. `UserProvider::refreshUser` déchiffre le secret et l'injecte dans l'instantané : `SecurityUser` ne détient pas `SecretBox`. Un test vérifie que la session sérialisée ne contient ni hash ni secret.
- **`UserChecker`** refuse un compte désactivé ou sans `account.login`, avec un message générique.
- **Firewall `main`** :
  - `form_login` avec CSRF ;
  - `login_throttling` avec un limiteur composite `symfony/rate-limiter` (décision 28) : compte + IP, 5 par 15 min, et IP, 50 par 15 min ;
  - logout en POST avec CSRF ;
  - pour un email inconnu, **un hachage Argon2id factice**, pour un temps de réponse égal.
- **Configuration scheb** :
  - le TOTP passe par un provider maison, `CommandBackedTotpProvider` : `leeway` à 1 fenêtre, délégation à `VerifyTotp`, rejeu refusé grâce à `lastAcceptedStep` ;
  - `HashedEmailCodeProvider` délègue à `VerifyEmailLoginCode` ;
  - `BackupCodeManager` délègue à `UseBackupCode` dans `isBackupCode()`, qui vérifie et consomme le code d'un même geste et sous verrou. `invalidateBackupCode()` est volontairement vide. C'est documenté et testé ;
  - `trusted_device` dure 30 jours, avec un cookie `__Host-depverify_trusted` (`Secure`, `Path=/`, sans `Domain`, `SameSite=Strict`), révoqué via `trustedDeviceVersion`.
- **Limiteurs du second facteur** (TOTP, code de secours, code email et ré-authentification). Ils comptent les **échecs** et sont consommés dans les handlers, sous le verrou `User`, via `AttemptThrottle` :
  - fenêtre courte : 5 échecs par 15 min, par compte et par IP. Au dépassement, le jeton 2FA en cours est annulé ;
  - **fenêtre longue : 20 échecs par 24 h par compte**. Au dépassement, le second facteur de ce compte est bloqué jusqu'à la fin de la fenêtre. Ce n'est pas un verrouillage du compte au sens de la décision 6, puisqu'il faut déjà connaître le mot de passe pour le déclencher. Deux **risques acceptés** sont consignés au cadrage §7 :
    - quelqu'un qui connaît ce mot de passe peut bloquer le second facteur du titulaire pendant 24 h ;
    - derrière un NAT, quelqu'un qui connaît un seul mot de passe peut bloquer pendant 15 min la fenêtre IP du second facteur de tous les collègues qui partagent cette IP ;
  - `User::noteSecondFactorThrottled()` enregistre un fait sans modifier d'état, puisque le compteur vit dans le limiteur et non dans l'agrégat. Ce choix est consigné dans le `CLAUDE.md`. Un test vérifie que l'événement est publié alors même que la racine n'a pas été modifiée ;
  - au premier blocage, c'est-à-dire quand `justExhausted` est vrai, le handler appelle `User::noteSecondFactorThrottled()`. L'**email d'alerte au titulaire** part alors après le commit : « votre mot de passe a été saisi correctement mais le second facteur a échoué à plusieurs reprises : changez votre mot de passe, cela stoppe l'attaque ». Un limiteur d'alerte (1 par 24 h et par compte) évite les doublons ;
  - les deux limites sont auditées.
- **Limiteur du mot de passe oublié** (`RateLimiterFactory`) : 3 demandes par heure par email normalisé, et 20 par heure par IP. Au dépassement, la réponse est **identique**, aucun email n'est envoyé, et l'événement est audité.
- **Ré-authentification** : elle demande le **mot de passe, puis le second facteur**, sauf si l'appareil est de confiance. Pour gérer le TOTP, on exige ainsi à la fois une connaissance et une possession, ou un appareil déjà approuvé.
- **`access_control`** :
  - publics : `/_healthcheck`, `/login`, `/password/forgot`, `/password/reset`, et la page d'arrivée `GET /invitations/{token}` ;
  - `/2fa*` exige `IS_AUTHENTICATED_2FA_IN_PROGRESS` ;
  - `POST /invitations/accept` exige `IS_AUTHENTICATED_FULLY` ;
  - `/admin` exige `IS_AUTHENTICATED_FULLY` et `ROLE_SUPER_ADMIN` ;
  - tout le reste exige `IS_AUTHENTICATED_FULLY`.
- **Jetons d'URL**
  - Au `GET`, la page d'arrivée résout le jeton par son hash. Elle met en session **l'id de l'`Invitation` ou de la `PasswordResetRequest`**, jamais le jeton brut, puis redirige vers une URL sans jeton (`/invitations/pending`, `/password/reset/new`).
  - Chaque étape suivante recontrôle l'objet par son id : il doit être en attente, non expiré et non consommé.
  - Avec `Referrer-Policy: no-referrer`, le jeton ne fuit ni par le `Referer` ni par l'historique.
  - Le log d'accès de Caddy masque le segment du jeton (filtre `regexp` sur `request>uri`).
  - Les routes publiques de ce parcours sont déclarées une par une : `GET /invitations/{token}`, `GET|POST /invitations/pending`, `GET /password/reset/{token}`, `GET|POST /password/reset/new`.
- **Sessions en base** (décision 29) :
  - **Connexion PDO propre.** `PdoSessionHandler` est construit avec un **DSN**. Il a donc sa propre connexion PDO, sous le rôle runtime, et ne reçoit **jamais** la connexion native de Doctrine (`getNativeConnection()`). Sa transaction ne se mélange ainsi jamais à celle d'une commande.
  - **Verrou.** On utilise `LOCK_ADVISORY` plutôt que la transaction tenue pendant toute la requête, ce qui convient mieux au mode worker.
  - **Droits et nettoyage.** Le rôle runtime reçoit `SELECT, INSERT, UPDATE, DELETE` sur `sessions` (le GC en a besoin). `gc_probability=1` et `gc_divisor=100` sont fixés explicitement.
  - **Cookie.** Il s'appelle `__Host-depverify_session` (`Secure`, `Path=/`, sans `Domain`). Cela interdit le *cookie tossing* depuis un sous-domaine voisin. On pose aussi `use_strict_mode: true`.
  - **Contenu.** La session ne contient que des ids, des horodatages et des hashes, jamais un jeton qui ouvre une porte. L'identifiant de session brut stocké en base est un **risque accepté**, consigné au cadrage §7 : il est borné à 12 h, révocable par `authVersion`, et la table n'est accessible qu'au rôle runtime.
  - **Durées.** **`SessionLifetimeSubscriber`** stocke la dernière activité et l'heure d'authentification via `ClockInterface`. Il applique lui-même les 30 min d'inactivité et les 12 h au total, ce qui le rend testable avec `MockClock`. Le GC PDO ne fait que nettoyer les sessions expirées.
  - **Test d'intégration.** Le vrai `PdoSessionHandler` tourne sous `depverify_app` : il écrit, relit et détruit une session, et vérifie les `GRANT`.
- **Limiteurs : mise en œuvre** (décision 28)
  - **Port.** `Shared\Application\Security\AttemptThrottle` expose deux méthodes :
    - `peek(ThrottleName, ThrottleSubject): ThrottleDecision` ;
    - `consume(ThrottleName, ThrottleSubject, int $tokens = 1): ThrottleDecision`.

    `ThrottleDecision` contient `accepted`, `retryAfter` et **`justExhausted`** (cette consommation vient de faire passer le reste à 0). `ThrottleSubject` est un value object (`forAccount(UserId)`, `forEmail(EmailAddress)`, `forIp(string)`, `forTeam(TeamId)`, `forInvitation(InvitationId)`) : on ne passe jamais une chaîne brute.

    Les handlers d'Application passent par ce port, jamais par `RateLimiterFactory`, ce qui respecte la liste blanche de `LayerDependencyTest`. Ce sont `VerifyTotp`, `VerifyEmailLoginCode`, `UseBackupCode`, `RequestPasswordReset`, `ResendInvitation` et `IssueEmailLoginCode`.
  - **Quand une commande ordinaire est limitée** (`RequestPasswordReset`, `ResendInvitation`, `IssueEmailLoginCode`, mais pas les vérifications de code). Le handler lève l'exception d'Application `Throttled`, que `AuditFailureMiddleware` audite une seule fois (`denied`, raison `throttled`). L'UI renvoie la même réponse qu'un succès quand l'anti-énumération l'exige (mot de passe oublié), et un message « réessayez plus tard » sinon. Un test vérifie qu'un dépassement ne produit qu'une seule entrée.
  - **Ordre des contrôles.** Pour `ResendInvitation`, on charge l'invitation, puis on vérifie la permission sur le propriétaire réel, et **seulement ensuite** on consomme le limiteur. Un acteur non autorisé ne peut donc pas épuiser le quota de renvoi de l'équipe.
  - **Adaptateur.** `SymfonyRateLimiterThrottle`, en Infrastructure, s'appuie sur les `RateLimiterFactory` nommées.
    - **`peek`** appelle `consume(0)` et calcule `accepted = getRemainingTokens() > 0`. Il **ne reprend jamais `isAccepted()`**, qui vaut toujours `true` pour 0 jeton (`SlidingWindowLimiter::reserve()`). Un test unitaire tourne sur un vrai `SlidingWindowLimiter` avec `InMemoryStorage` : après 5 `consume(1)`, `peek` doit être refusé.
    - Les clés passent par `TokenHasher` (HMAC), avec la clé courante uniquement. Le stockage ne contient donc jamais d'email ni d'IP en clair. La documentation précise qu'une rotation du pepper remet les fenêtres à zéro.
  - **`login_throttling`** utilise un service `LoginRateLimiter`, construit sur le modèle de `DefaultLoginRateLimiter`. Il compose les deux factories nommées (compte + IP : 5 par 15 min ; IP : 50 par 15 min), qui portent elles-mêmes le stockage et le `lock_factory` ci-dessous. La règle d'échec fermé s'applique donc aussi au login.
    - **`reset(Request)` est surchargé** pour ne remettre à zéro que le limiteur compte + IP, **jamais celui de l'IP seule**. Sans cela, `AbstractRequestRateLimiter::reset()` remettrait les deux à zéro à chaque connexion réussie, et un attaquant qui possède un compte valide pourrait vider le compteur IP. Un test fonctionnel couvre ce cas : 49 échecs sur des comptes différents depuis une même IP, une connexion réussie, puis la tentative suivante est refusée.
    - Ses clés (email normalisé, IP) passent par `TokenHasher` **avant** la création du limiteur. L'id stocké dans l'état sérialisé est donc lui aussi haché, et `rate_limiter_state` ne contient d'email ni d'IP en clair, ni dans `id` ni dans `state`. Un test le vérifie.
  - **Stockage dédié, en échec fermé et hors de la transaction métier.** **`DbalRateLimiterStorage implements StorageInterface`** écrit directement dans la table `rate_limiter_state` (`id` haché, `state`, `expires_at`), via la **connexion Doctrine dédiée `rate_limiter`**, en autocommit et sous le rôle runtime. Il n'y a ni pool de cache ni adaptateur qui avale les erreurs :
    - les exceptions DBAL remontent, et **le stockage ne retente jamais** : sa connexion porte aussi les verrous advisory. Il lève directement `RateLimiterStorageUnavailable`, et la requête est refusée (503 générique) et journalisée ;
    - l'audit écrit une seule entrée : un `failure` de raison `throttle.storage_failed` pour une commande du bus, ou une entrée `throttle.storage_failed` dédiée pour `login_throttling`, qui passe par le firewall ;
    - `peek` lit le stockage. Une panne lève donc l'exception dès `peek`, et non seulement à `consume(1)` ;
    - l'état est désérialisé avec `allowed_classes` limité aux classes d'état du limiteur ;
    - un rollback de la commande ne rend jamais un jeton consommé.

    Tests d'intégration sous `depverify_app` :
    - connexion `rate_limiter` coupée : `peek` lève l'exception, le login est refusé et audité, et la vérification 2FA est refusée ;
    - la commande échoue mais la consommation reste acquise ;
    - un `save` est bien persisté.
  - **Atomicité entre workers.** On ajoute `symfony/lock` avec un store `DoctrineDbalPostgreSqlStore` construit sur **la connexion DBAL `rate_limiter` elle-même** (verrous advisory). Il n'y a donc pas de quatrième connexion par worker, ce qui reste conforme au dimensionnement. `lock_factory: lock.factory` est posé sur chaque limiteur. `SecondFactorAttempt` verrouille aussi la clé IP, via `ExclusiveSection`, pendant toute la séquence `peek` / vérification / `consume`. Test de concurrence : N mauvais codes envoyés en parallèle, sur un compte ou sur plusieurs comptes depuis la même IP, donnent **au plus 5 `Rejected` évalués**, puis des `Throttled`.
  - **Premier blocage du 2FA sur 24 h** : voir `User::noteSecondFactorThrottled()`. Un test vérifie qu'un seul email d'alerte part, après le commit.
  - **Purge.** La commande `app:rate-limiter:prune` supprime les lignes dont `expires_at` est dépassé. Elle est lancée par `make rate-limiter-prune` et documentée. Sa planification relève du même non-objectif que `maintain-partitions`.
- **Régénération de l'id de session** à la fin du second facteur et après chaque `/reauthenticate`, mécanisme maison qui appelle `migrate(true)` explicitement. Un test vérifie que l'id diffère avant et après.
- **Ré-authentification** : l'attribut `#[RequiresRecentAuthentication]` et son listener redirigent vers `/reauthenticate`. Le retour n'accepte **qu'un nom de route interne** stocké en session, jamais une URL fournie par le client. La même règle vaut pour `_target_path` au login, ce qui empêche toute redirection ouverte. Ce contrôle ne protège que l'UI, ce qui est documenté pour les futurs points d'entrée.
- **En-têtes de cache** : les pages qui affichent les codes de secours, le QR code ou le secret TOTP posent `Cache-Control: no-store`, et un test le vérifie.
- **Audit de l'authentification** : un subscriber audite chaque connexion réussie et chaque échec (raison classée, sans l'email saisi s'il est inconnu), la déconnexion, le déclenchement d'une limite et l'enregistrement d'un appareil de confiance. Si l'écriture d'audit échoue à cet endroit, l'erreur est journalisée sans bloquer la connexion. Ce **risque accepté** est consigné dans le cadrage §7.

**Infrastructure : emails et CLI**

- `symfony/mailer` avec les templates `templates/email/identity/*.html.twig` et leur version texte. L'envoi est différé et vidé en `kernel.terminate` **et** en `console.terminate`.
- Le service `mailpit` est ajouté dans `compose.override.yaml`.
- **`app:user:create-super-admin`** :
  - mot de passe saisi de façon masquée, ou lu dans `--password-file`, qui est refusé s'il est lisible par d'autres que le propriétaire ;
  - le mot de passe n'est jamais affiché ;
  - le compte reçoit le statut super admin et `account.login` ;
  - l'acteur enregistré est `cli`.
- Le QR code du TOTP est généré localement en SVG par `endroid/qr-code`, et le secret est aussi affiché en texte.

**UI**

- Layout `auth` : connexion, second facteur (InputOTP, « Resend code », « Trust this device for 30 days », lien vers un code de secours), mot de passe oublié et réinitialisation, ré-authentification, acceptation d'une invitation.
- « Account security » : changement de mot de passe, TOTP (QR code puis confirmation), codes de secours affichés une seule fois.
- `/admin/users`.
- Les previews sont supprimées.

### Organization (commit 3)

**Domaine (`Organization\Domain\Model`)**

| Élément | Contenu |
|---|---|
| `InstanceSettings` | Singleton qui porte les quotas par défaut, en `TeamQuotas`. |
| `Quota` | `unlimited()` ou `of(n)`, avec `allows(usage)` et `ratio(usage)`. Pas de `null` exposé. |
| `TeamQuotas` | Les 9 quotas de §5ter. |
| `Team` | Racine de `TeamMembership`. Elle porte `TeamId`, `name`, un `slug` fourni, `TeamQuotas` et **`adminEstablished`**, posé au premier `admit` d'un `TEAM_ADMIN`. Méthodes : `rename()`, `changeQuotas()`, `admit(userId, role, now)`, `changeRole(...)` et `removeMember(...)`. |
| `Project` | Racine de `ProjectMembership` et d'`Environment`. Elle porte `teamId`, `name` et un `slug` unique par équipe. Elle se crée par `Project::create(id, teamId, name, slug, creatorId, TeamRole $creatorRole, now)`, qui porte la règle du créateur. Méthodes : `rename()`, `admit` (même verbe que `Team`), `changeRole`, `removeMember`, `addEnvironment`, `renameEnvironment`, `removeEnvironment` et `delete()`. |
| `Environment` | Entité interne de `Project`. Elle porte `name`, unique par projet sans tenir compte de la casse, et `isProduction`. |
| `TeamMembership` | `userId`, `teamId`, `role` (enum `TeamRole`), `extraPermissions` et `status` (`active` ou `suspended`). |
| `ProjectMembership` | `userId`, `projectId`, `role` (enum `ProjectRole`), `extraPermissions` et le même `status`. |
| `PermissionGrant` | Historique métier en ajout seul, affiché dans l'UI. L'audit, lui, est la trace de sécurité. Les deux sont écrits dans la même transaction. |
| `Invitation` | `accept(email, now)`, `revoke()`, `reissue(newHash, now)` et `isExpiredAt(now)`. `issue` enregistre `InvitationIssued`, et `reissue` enregistre `InvitationReissued` : l'envoi de l'email passe par le même chemin, après le commit. Le statut stocké vaut `pending`, `accepted` ou `revoked`. **L'expiration est calculée, jamais stockée.** |
| Méthodes complémentaires | Sur `Team` : `suspendMember`, `restoreMember`, `grantExtra`, `revokeExtra`. Sur `Project` : `suspendMember`, `restoreMember`, `grantExtra`, `revokeExtra`, `updateEnvironment(name, isProduction)`. Sur `InstanceSettings` : `changeDefaultQuotas`. `Team::changeRole` et `Team::removeMember` **appliquent eux-mêmes** `KeepsATeamAdmin`, pour que l'invariant reste dans la racine. `suspendMember` en est exempté : la désactivation par le super admin est autorisée. |

- **Membre actif** : un membre dont la membership est `active`. Un membre suspendu ne compte ni pour `maxMembers` ni pour « au moins un `TEAM_ADMIN` ».
- **Créations par constructeurs nommés.**
  - `Team::create(id, name, slug, TeamQuotas $defaults, now)` copie les quotas par défaut.
  - `Invitation::issue(id, email, target, role, tokenHash, invitedBy, now)` crée l'invitation.
- **Désactivation et réactivation d'un compte.** Organization consomme `AccountDeactivated` et `AccountReactivated`. Ses handlers d'événement se contentent d'envoyer les commandes **`SuspendMembershipsOfUser(userId)`** et **`RestoreMembershipsOfUser(userId)`**, avec l'acteur `system`.
  - Depuis l'admin, « Re-sync memberships » exige `instance.users.manage`. L'UI lit `GetUserProfile`, puis envoie Suspend ou Restore selon le statut du compte.

  Ces commandes :
  - sont idempotentes : suspendre un membre déjà suspendu ne fait rien ;
  - sont auditées ;
  - verrouillent chaque équipe concernée, dans l'ordre des `teamId`.

  Si la cascade échoue, l'échec est audité (`event.handler.failed`) et journalisé. L'état reste incohérent (compte désactivé, memberships actives) jusqu'à ce que la commande soit rejouée, ce qu'on peut faire depuis `/admin/users` (« Re-sync memberships »). Un test d'intégration couvre cet échec.

  Une réactivation peut faire dépasser `maxMembers`. Rien n'est refusé, comme lorsqu'un quota est abaissé : la jauge dépasse 100 % et les nouvelles entrées sont bloquées.

  Le super admin peut désactiver le dernier admin d'une équipe. L'équipe n'est alors plus gérée que par le super admin, et l'opération est auditée.
- **Projet vide.** Dans ce step, un projet est vide s'il n'a **aucun environnement**.
  - Pour le supprimer, le handler de `DeleteProject` interroge d'abord les sondes de contenu, puis appelle `Project::delete()`.
  - Les invitations en attente du projet sont révoquées par `Invitation::revoke()`, dans la même transaction et sous le verrou d'équipe. Un environnement est supprimable tant qu'aucun contexte ne déclare de contenu.

  Pour plus tard, on prévoit un port Shared **`ProjectContentProbe`** (et `EnvironmentContentProbe`), sur le modèle de `HealthProbe` (`#[AutoconfigureTag]` et `#[AutowireIterator]`). Chaque futur contexte (Fleet, Inventory, Exposure) l'implémentera, et la suppression sera refusée dès qu'une sonde signale du contenu. La liste est vide dans ce step, et un test vérifie qu'une sonde factice bloque bien la suppression.
- **Index unique partiel sur les invitations** : `(email, target_type, target_id) WHERE status = 'pending'`. `InviteMember` révoque d'abord automatiquement une invitation en attente mais expirée pour la même cible, puis en crée une nouvelle.

**Règles**

- **`RolePermissions`** est la table unique des rôles. Elle liste, pour chaque rôle, les permissions accordées par défaut (✓) et celles qui peuvent être ajoutées (○). Le resolver, l'UI et les tests s'en servent.
- **`PermissionResolver`** est pur : il prend en entrée l'acteur et ses memberships, et renvoie les permissions effectives (rôle d'équipe + extras d'équipe + rôle projet + extras projet, le super admin court-circuitant le calcul). En Infrastructure, le **décorateur `RequestScopedPermissionResolver`** met ce calcul en cache pour la durée de la requête et implémente `ResetInterface`. Il est aussi vidé après chaque commande d'Organization, ce qui évite un cache périmé quand un rôle change pendant la requête.
- **Specifications composables**, avec un test unitaire chacune :
  - `RoleAssignable`, qui s'appuie sur `TeamRole::canAssign()` et `ProjectRole::canAssign()` (décision 15) ;
  - `ExtraGrantable` (○ pour ce rôle, et l'accordant détient lui-même la permission ; les permissions d'instance ne s'ajoutent jamais) ;
  - `KeepsATeamAdmin` : au moins un `TEAM_ADMIN` actif dès que `Team::adminEstablished` est vrai, **sauf** pour une suspension consécutive à la désactivation d'un compte ;
  - `RequiresTeamMembership`.
- **Règle de création** : le créateur d'un projet devient `PROJECT_ADMIN`, sauf si son rôle d'équipe le couvre déjà. Cette règle est appliquée dans l'opération de création.
- **`QuotaPolicy`** bloque strictement à 100 %, super admin compris, et sous le verrou de l'équipe. En cas de dépassement, elle lève **`QuotaExceeded(quotaName, limit)`**, de la famille `BusinessRuleViolated`, auditée en `denied` avec la raison `rule:quota`. `ActionResponder` la traduit en un seul point par une 422, avec le message « Quota de N … atteint, contactez l'administrateur de l'instance ». Elle applique `maxProjects`, `maxEnvironmentsPerProject` et `maxMembers` (memberships actives + invitations en attente non expirées). Les autres quotas sont stockés et modifiables, mais seront appliqués par leurs contextes.

**Application**

- **Commandes**, toutes auditables, et dont chaque handler revérifie la permission sur le propriétaire réel de l'objet :
  - instance : `UpdateDefaultQuotas`, qui ne s'applique qu'aux équipes créées ensuite (les équipes existantes gardent leur copie) ;
  - cascade : `SuspendMembershipsOfUser`, `RestoreMembershipsOfUser` ;
  - équipe : `CreateTeam(teamId, name, firstAdminEmail)`, `RenameTeam`, `UpdateTeamQuotas` ;
  - projets : `CreateProject`, `RenameProject`, `DeleteProject` ;
  - environnements : `CreateEnvironment`, `UpdateEnvironment`, `DeleteEnvironment` ;
  - invitations : `InviteMember`, `ResendInvitation`, `RevokeInvitation` et `AcceptInvitation` (le contrat). `ResendInvitation` est limité via `AttemptThrottle`, après le contrôle de permission : 3 renvois par heure par invitation et 30 par heure par équipe. Les dépassements lèvent `Throttled` et sont audités une seule fois ;
  - membres : `ChangeTeamRole`, `ChangeProjectRole`, `GrantExtraPermission`, `RevokeExtraPermission`, `RemoveTeamMember`, `RemoveProjectMember`.
- **Événements** : `InvitationIssued` et `InvitationReissued`, avec le jeton en clair en mémoire seulement, jamais sérialisé. Tous deux déclenchent `InvitationSender`, un port propre à Organization, après le commit.
- **Requêtes** : `ListMyTeams`, `GetTeamOverview`, `ListProjects` (filtrée par portée), `GetProject`, et le contrat `FindPendingInvitation` (qui renvoie l'email, le nom de la cible et le rôle).

**Parcours d'invitation**

L'orchestrateur explicite est **le contrôleur d'Identity `InvitationController`** :

1. `GET /invitations/{token}` échange le jeton contre une valeur en session, puis redirige vers `/invitations/pending`.
2. `/invitations/pending` interroge `FindPendingInvitation`, puis :
   - si l'utilisateur est connecté avec le même email, il affiche « Accept » ;
   - si un compte complet existe pour cet email, il propose de se connecter et le login revient sur la page ;
   - sinon, l'utilisateur définit son mot de passe (`ActivateInvitedAccount`), se connecte, passe le 2FA par email, puis revient sur la page.

   La page affiche le même texte dans ces trois cas.
3. `POST /invitations/accept` envoie `AcceptInvitation`. Le handler :
   - verrouille l'équipe ;
   - contrôle l'invitation (`accept(email, now)`) ;
   - revérifie le quota ;
   - crée la membership, plus une TeamMembership `TEAM_GUEST` si c'est une invitation de projet ;
   - écrit le `PermissionGrant`.

   L'acceptation est **idempotente** : si la membership existe déjà, l'invitation est marquée acceptée et aucune erreur n'est levée.
4. **Compte activé mais acceptation refusée** (quota atteint entre-temps) : c'est un état assumé. On affiche le message de quota, l'invitation reste en attente, et on peut réessayer plus tard.

**Infrastructure et UI**

- `TeamVoter` et `ProjectVoter` traitent les attributs `Permission` sur une `TeamId` ou une `ProjectId`, et délèguent au resolver décoré.
- Les repositories filtrent par portée.
- Les URLs reposent sur l'UUID, comme `/teams/{teamId}/projects/{projectId}`.
- Écrans d'équipe : membres et rôles, invitations, permissions additionnelles (uniquement les ○), jauges de quota avec un bandeau à 80 %, projets et environnements.
- Écrans d'admin : équipes et quotas par défaut.
- `AppSidebar`, `TeamSwitcher` et `NavUser` sont branchés sur les données réelles.
- On ajoute au kit les composants `alert`, `checkbox`, `select`, `table`, `input-otp`, `switch` et `skeleton`.

### UI : Turbo Frames, placeholders et Turbo Streams (décision 31, transverse)

`symfony/ux-turbo` est déjà installé : Turbo Drive est actif.

**Une seule recette par frame, un seul juge**

- **Interface et enums.** `Shared\UI\Frame` est une interface : `id()`, `route()` et `fallbackRoute(FrameContext): RouteReference`. Chaque contexte l'implémente par un enum `TurboFrame`, dont les cases portent ces **méthodes de présentation**.
  - `fallbackRoute` désigne une page **du même contexte** que la frame, construite avec les paramètres tirés de `FrameContext`. C'est la page qui affiche cette frame seule, dans le layout. Exemple : Audit possède sa page `/teams/{teamId}/audit`, qui sert de repli à la frame d'audit d'équipe.
  - Une frame ne connaît donc jamais la page d'un autre contexte qui l'embarque.
  - Le data provider des tests vérifie que chaque `fallbackRoute` appartient au contexte de la frame ou à `Shared`.
- **`FrameView`.** Chaque case a **une seule** implémentation de `FrameView::render(FrameContext): string` (Strategy). Elle interroge le `query.bus` et rend le template.
  - **Le handler de requête est le seul juge** de la portée et de la permission. `FrameView` n'appelle pas de voter. En cas de refus, le handler lève `PermissionDenied` ou `ResourceNotFound`, et `AuditDeniedQueryMiddleware` l'audite une seule fois.
  - Le `is_granted(…)` côté Twig ne sert qu'à éviter une requête inutile : une frame interdite n'est pas incluse dans la page.
  - L'endpoint lazy **et** le stream composent ce même `FrameView`.
- **Rendu des refus.** Un **`FrameExceptionRenderer`** unique (listener `kernel.exception` limité aux routes `frames`) enveloppe le refus dans `<turbo-frame id="…">`, avec son statut : 403, 404, 422, 503 ou 500. Il ne réaudite rien, puisque l'exception est déjà auditée (voir plus bas).
- **Page hôte.** Elle ne référence que le **nom de route** de la frame, celui du `RouteCollection` du contexte propriétaire. L'identifiant DOM est rendu par l'endpoint.
  - Par exemple, la page d'équipe (Organization) embarque la frame d'audit d'équipe (Audit) par son seul nom de route, ce qui respecte `LayerDependencyTest`.
  - Un test vérifie que chaque nom de route référencé par une page hôte existe.

**Frames lazy**

- **Squelette de page.** La page rend tout de suite son squelette (layout, en-tête, breadcrumb), puis une `<turbo-frame id src loading="lazy">` par zone lourde.
  - Chaque frame contient un **placeholder** fait de lignes `Skeleton`, aux dimensions proches du contenu final.
  - Elle contient aussi un `<template>` d'erreur traduit (« Couldn't load this section » et « Retry »), **rendu par le serveur** (décision 22).
- **Endpoints.** Ce sont des contrôleurs invocables, sur des routes `…/frames/<nom>`. Ils appliquent les mêmes contrôles que la page :
  - 404 hors portée, 403 si l'objet est visible mais que la permission manque ;
  - rendu **toujours** dans `<turbo-frame id="…">`, état vide compris : une phrase et l'action principale ;
  - en-têtes `Cache-Control: private, no-store` et `Vary: Accept, Turbo-Frame` ;
  - appelé sans en-tête `Turbo-Frame`, l'endpoint **redirige en 303 vers `fallbackRoute()`**.

  Une frame n'est jamais une porte dérobée.
- **Retour après connexion.** Une route de frame n'est **jamais** enregistrée comme chemin de retour : le `TargetPathSubscriber` ignore les requêtes qui portent `Turbo-Frame` ou visent une route `frames`.
- **Journal d'audit.**
  - **Curseur.** C'est un value object **`AuditCursor`** : décodé une seule fois, avec un horodatage et un UUID validés. Un curseur invalide donne une 422.
  - **Filtres.** Ils sont en **liste blanche**, et passés à la requête en paramètres liés.
  - **Équipe.** Le `team_id` vient **toujours de la route**, après le voter, jamais de la query string.
  - **Liens de curseur.** Ils pointent vers l'URL de la **page** (`/teams/{teamId}/audit?cursor=…`), avec `data-turbo-frame="audit"` et `data-turbo-action="advance"`. Un rechargement affiche donc la page complète.
  - **Test.** La frame d'audit fait partie du test à deux équipes.
- **États côté navigateur.** Le contrôleur `frame_state_controller.ts` est écrit en TypeScript, sans script inline, et s'appuie sur les événements de Turbo 8.
  - **`turbo:frame-missing`.** Un seul handler. Il appelle `preventDefault()`, puis tranche sur `detail.response` :
    - si la réponse est `redirected` ou `ok`, il vide le cache (`Turbo.cache.clear()`) puis fait une visite complète, **seulement si l'URL a la même origine**, sinon il recharge la page ;
    - si c'est une 5xx, il affiche le `<template>` d'erreur avec « Retry ».
  - **`turbo:fetch-request-error`.** Il affiche le même état d'erreur, pour que le placeholder ne reste jamais affiché indéfiniment.
  - **Dialogs.** `turbo:submit-end->dialog#closeOnSuccess` lit `event.detail.success`.

**Cache de pages de Turbo, prefetch et CSP**

- **Cache de pages.** Le layout authentifié (`templates/shared/layout/app.html.twig`) porte `<meta name="turbo-cache-control" content="no-cache">`, car `Cache-Control: no-store` est ignoré par ce cache. Un retour arrière ne réaffiche donc jamais une page authentifiée sans requête au serveur.
  - Le logout reste un POST, ce qui purge le cache, et c'est documenté.
  - Un test vérifie la présence de la balise.
- **Prefetch.** `<meta name="turbo-prefetch" content="false">`.
- **CSP.**
  - **Nonce.** Le service `CspNonce` (`ResetInterface`, mode worker) génère un nonce par requête. Il est exposé dans `<meta name="csp-nonce">` pour la barre de progression de Turbo, avec `style-src 'self' 'nonce-…'`.
  - **Pas d'`'unsafe-inline'`**, ni pour les scripts ni pour les styles.
  - **Attributs `style` du kit.** On en compte trois : deux dans `Tooltip/Content.html.twig` (L19 et L40) et un dans `Sidebar/MenuSkeleton.html.twig` (L15, variable CSS `--skeleton-width`). Ils sont **remplacés par des classes**. Pour `--skeleton-width`, on utilise des paliers de largeur (`w-1/2`, `w-2/3`, `w-3/4`…), ou on la pose en CSSOM depuis un contrôleur Stimulus, ce que la CSP autorise.
  - **Jauges de quota.** Elles utilisent l'élément natif `<meter>`, sans aucun style inline.
  - **Test.** Un test sur le HTML rendu vérifie qu'aucun template de l'espace authentifié ne contient d'attribut `style=`.
- **CSRF.** Ce sont des jetons stateful, gérés par le composant Form, y compris pour les boutons (`ActionButtonType`, avec un `csrf_token_id` par action). Le relais d'en-tête de `csrf_protection_controller.ts` (`check_header`) n'est pas utilisé, et c'est documenté.

**Actions : `ActionResponder`, un seul point de réponse**

- **Le contrôleur.** Il reste un douanier :
  - il valide le formulaire ;
  - il construit la commande et l'envoie sur le bus ;
  - il confie **toute** l'action à **`Shared\UI\ActionResponder::handle(ActionForm $form, \Closure $toCommand, ResponseFormat $format, RouteReference $fallback)`** (*execute around*, principe Hollywood).
    - **`ActionForm`** est un value object qui réunit le `FormInterface` (un vrai formulaire, ou un `ActionButtonType` sans champ), la `Frame` du formulaire et son template. Le responder sait donc où et comment re-rendre le formulaire.
    - La fermeture `$toCommand` reçoit les données validées et renvoie une **`AuditableCommand`**, vérifiée par PHPStan au niveau max.
    - **`ResponseFormat`** est la Strategy passée explicitement : `StreamOrRedirect`, la valeur par défaut, ou `SecretRevealingResponse`.

    Le responder déroule l'action entière, en un seul point :
    1. **Jeton CSRF invalide** : c'est l'erreur de `getErrors(true)` dont `getCause()` est un `CsrfToken`. Elle est confiée au collaborateur **`CsrfRejection`**, partagé avec les pages d'authentification et testé seul. Il rend une **403** et écrit **une seule** entrée : l'action `csrf.rejected`, en `denied`, avec `Scope::none()`. Son contexte en liste blanche ne contient que le `csrf_token_id`, jamais les données du formulaire. Une tentative CSRF ne se confond donc pas avec une faute de saisie.
    2. **Formulaire invalide** pour une autre raison : 422 dans la frame du formulaire, sans aucun `dispatch` ni audit.
    3. **Contrôle de cohérence, avant tout `dispatch`.** La commande est construite par `$toCommand`. Le responder vérifie ensuite l'accord entre `RevealsSecret` et la Strategy `ResponseFormat`. En cas d'incohérence, il lève une `LogicException` **avant** le `dispatch` : rien n'est committé, et un lot de codes ne peut pas être révoqué sans que le nouveau soit affiché.
    4. **`dispatch`** sur le `CommandBus`, dans un `try`.
    5. **Refus** : il attrape `AlreadyAudited`, lit `cause()`, puis applique la table des refus ci-dessous. Le formulaire est **re-rendu avec ses saisies** et l'erreur, dans sa frame, avec le statut de la table. Les champs de mot de passe utilisent toujours `PasswordType` avec `always_empty: true`. Les codes générés côté UI ne sont jamais des champs de formulaire. Une 422 ne renvoie donc jamais de mot de passe ni de code, et un test le vérifie. L'entrée d'audit est déjà écrite : rien n'est réaudité.
    6. **Succès** : la réponse est produite par la Strategy `ResponseFormat` reçue, avec le rafraîchissement des frames pour `StreamOrRedirect`.

    Le contrôleur n'a donc ni `try/catch`, ni entrée facultative, ni `null` implicite.
  - **Composition.** `ActionResponder` est une façade qui compose deux éléments, testés chacun seul :
    - un **`FrameRefresher`**, qui lit `ActionFrameMap`, contrôle la visibilité et produit les `replace`, `remove` ou états d'erreur ;
    - une Strategy **`ResponseFormat`**, qui choisit entre stream et 303.
- **Frames à rafraîchir.** Le **responder** lit les tables « action → frames » à partir de l'`AuditAction` de la commande.
  - Les tables sont agrégées par le port Shared **`ActionFrameMap`**, déclaré avec `#[AutoconfigureTag]` et `#[AutowireIterator]`, sur le modèle de `HealthProbe`.
  - Chaque contexte fournit sa table, qui ne contient que **ses propres** frames. Une table peut associer l'`AuditAction` d'un autre contexte à l'une de ses frames : Audit déclare ainsi que `RemoveTeamMember` rafraîchit sa frame d'audit d'équipe. Aucun contexte n'importe une frame d'un autre.
  - Les tables sont couvertes par les tests d'action.
- **Visibilité après l'action.** Avant de recomposer une frame, le responder vérifie qu'elle est **encore visible** pour l'acteur. Il utilise le même `is_granted` que la page, un contrôle non audité.
  - Une frame devenue invisible reçoit un stream **`remove`**, sans relecture et sans entrée `denied`. C'est le cas quand l'acteur s'est retiré ou rétrogradé lui-même.
  - Si plus rien de la page n'est visible, la réponse est une 303 vers une route que l'acteur peut voir, par exemple `/`.
  - Un test le vérifie : un acteur se retire lui-même, la réponse est un stream valide, avec exactement une entrée `success` et aucune `denied`.
- **Ce qui est commité ne se dément pas.** L'issue de la **commande** fixe le statut de la réponse et son `Alert`. Chaque frame est ensuite recomposée **isolément**. Si l'une d'elles échoue, par exemple sur une 503 de la base pendant la relecture ou sur une divergence entre le voter et le handler :
  - la réponse reste **200**, avec l'alerte de succès ;
  - la frame en échec reçoit un `replace` par son `<template>` d'erreur, avec « Retry » ;
  - l'échec est journalisé.

  Une erreur pendant la relecture n'écrit **aucune entrée `failure` sur la commande**, qui reste `success`. C'est la même règle que pour `PublishDomainEventsMiddleware` : une réaction qui échoue ne requalifie jamais l'effet validé.

  En revanche, **un `denied` écrit par `AuditDeniedQueryMiddleware` pendant la relecture reste écrit**. Il signale une divergence entre le voter et le handler, c'est-à-dire une autorisation incohérente. On peut faire taire l'alarme, pas effacer le fait qu'elle a sonné. Le responder absorbe l'exception (`AlreadyAudited`) sans réauditer.

  Le journal applicatif de l'échec ne contient que **la classe de l'exception, l'id de la frame et le request id**. Il ne contient jamais le message de l'exception ni le contenu rendu.

  Deux tests le vérifient :
  - une commande réussie dont une frame échoue en 503 renvoie une 200, avec une seule entrée `success`, et la frame est en état d'erreur ;
  - une divergence entre le voter et le handler pendant la relecture donne `success` sur la commande, plus une entrée `denied` sur la requête.
- **Format de la réponse** (Strategy) :
  - **Turbo Stream** quand la requête accepte `text/vnd.turbo-stream.html`. Il contient un `replace` par frame visible (même `FrameView`, relu par le `query.bus` après le `dispatch`), plus un `append` d'un `Alert` ;
  - **redirection 303** sinon, **sauf** pour les actions qui affichent un secret (voir ci-dessous).
- **Refus.** Une **seule table de correspondance**, avec son test unitaire qui énumère tous les cas. Le refus est rendu dans la frame du formulaire.

  | Cas | Statut | Audit |
  |---|---|---|
  | Erreur de validation (avant `dispatch`) | 422 | — |
  | **`BusinessRuleViolated(ruleKey)`**, la famille des refus métier : `QuotaExceeded`, `LastTeamAdminRequired`, `ProjectNotEmpty`, `EnvironmentNotEmpty`, `DuplicateEnvironmentName`, `InvitationEmailMismatch`, `InvitationAlreadyPending`, `AlreadyMember`, `InvalidSecondFactorTransition`, `SuperAdminRevocationForbidden` | 422, avec une clé de traduction tirée de `ruleKey` | `denied` / `rule:<ruleKey>` |
  | `PermissionDenied` | 403 | `denied` |
  | `ResourceNotFound` | 404 | `denied` |
  | `Throttled` | 429 | `denied` / `throttled` |
  | Violation d'unicité, par exemple une double soumission avec le même id généré par l'UI | 409 (« already done ») | `failure` / `conflict` |
  | `RateLimiterStorageUnavailable`, délai de verrou dépassé (55P03) | 503 | `failure` / `technical` |
  | Tout autre cas | 500 générique, dans la frame | `failure` / `technical` |
  | Échec de recomposition d'une frame **après** une commande réussie | 200, avec l'alerte de succès et cette frame en état d'erreur | aucune entrée `failure` sur la commande (qui reste `success`). Un `denied` déjà écrit par `AuditDeniedQueryMiddleware` reste en place |

  **`BusinessRuleViolated`** vit dans **`Shared\Domain`**, car les Domains de chaque contexte la lèvent. `PermissionDenied`, `ResourceNotFound` et `Throttled` restent en `Shared\Application`.

  **Les pages d'authentification ne passent pas par `ActionResponder`.** C'est le cas en particulier du mot de passe oublié, qui renvoie toujours la réponse de succès pour ne rien révéler.

  **Les frames d'un autre contexte présentes sur la même page** ne sont rafraîchies que si leur contexte le déclare dans son `ActionFrameMap`. Sans cela, elles se mettent à jour au prochain chargement. C'est assumé, puisqu'il n'y a pas de temps réel (décision 31).

  Les Turbo Streams ne transportent que du HTML rendu par Twig, échappé automatiquement et relu par les mêmes requêtes filtrées par portée.
- **Actions qui affichent un secret.** Il y en a deux : `RegenerateBackupCodes`, et `ConfirmTotp`, qui affiche les premiers codes. Elles passent **elles aussi par `ActionResponder::handle()`**, avec la Strategy `SecretRevealingResponse`. Leurs refus (`InvalidSecondFactorTransition`, échec technique…) suivent donc la même table des refus.
  - **Garde-fou dans les deux sens.** Ces commandes implémentent l'interface marqueur **`RevealsSecret`**. `handle()` lève une `LogicException` dans deux cas :
    - une commande `RevealsSecret` arrive avec une autre Strategy que `SecretRevealingResponse` ;
    - `SecretRevealingResponse` est utilisée pour une commande qui n'est pas `RevealsSecret`.

    Ces deux cas sont testés. Un oubli échouerait d'ailleurs fermé, puisque rien ne passe par la session.
  - **Code TOTP faux à la confirmation.**
    - **La commande.** `ConfirmTotp(userId, code, attemptId, backupCodes)` est une `SelfAuditedCommand` qui passe par `SecondFactorAttempt`, avec la Strategy **`TotpEnrollmentCheck`**. Celle-ci appelle `User::confirmTotp`, et non `verifyTotp`, qui serait une transition invalide sur `PendingTotp`.
    - **Le résultat.** Un code faux donne `Rejected`, compté par les limiteurs du second facteur. Une seule entrée `failure` est écrite, et `AuditSuccessMiddleware` n'en ajoute pas.
    - **L'affichage.** `SecretRevealingResponse` **lit `GetCodeVerificationOutcome(attemptId)` après le `dispatch`**. Les codes de secours ne sont affichés que sur `Accepted`.
      - `Rejected`, `Exhausted` ou `Expired` donnent une 422, et `Throttled` une 429, dans la frame du formulaire, **sans aucun code**.
      - Le TOTP reste `PendingTotp`, et aucun hash de code de secours n'est enregistré.
      - Les codes générés côté UI pour cette tentative sont simplement jetés.
    - **Le test.** Un code faux donne une 422, exactement une entrée `failure`, aucun code dans la réponse, et l'état reste `PendingTotp`.
  - **Génération.** Les codes en clair sont générés **côté UI** par le port `BackupCodeGenerator`, comme les ids. Ils sont passés dans la commande (`RegenerateBackupCodes` et `ConfirmTotp`), qui ne stocke que leurs hashes. Ils n'existent ensuite que dans la réponse du POST.
  - **`#[\SensitiveParameter]`** marque tout paramètre de commande qui transporte un secret en clair : codes de secours, mots de passe (`ChangePassword`, `ResetPassword`, `ActivateInvitedAccount`, `CreateSuperAdmin`) et codes de vérification. Aucune trace de pile n'en contient donc la valeur, même avec un `php.ini` de dev. Un test d'architecture vérifie que toute propriété de commande nommée `*code*`, `*password*` ou `*secret*` porte l'attribut.
  - **Formulaires.** Ils sont en **`data-turbo="false"`**. La réponse est rendue en **200**, avec `Cache-Control: no-store` et la balise `turbo-cache-control` à `no-cache`. Ces actions **sont exclues du repli 303** : aucun flash, aucune donnée en session, aucun stockage intermédiaire.
  - **Test.** Après la régénération, la table `sessions` et l'audit ne contiennent aucun code, et une redirection n'affiche jamais les codes.
- **Pages d'authentification.** Ce sont les sept routes listées plus haut. Elles restent des pages classiques, en `data-turbo="false"`.
  - Leurs contrôleurs n'utilisent pas `ActionResponder`, mais ils **lisent eux aussi `AlreadyAudited::cause()`**, par exemple pour `Throttled` sur `RequestPasswordReset` ou `IssueEmailLoginCode`, et ne réauditent jamais.
  - Ils **réutilisent la même table de correspondance des refus** pour le statut et la clé de traduction. Le rendu, lui, est propre à ces pages : par exemple, le mot de passe oublié renvoie toujours la réponse de succès.
  - Leur CSRF passe par `CsrfRejection`.
  - Le test « une seule entrée par refus » les couvre aussi.

**Audit des refus, un seul point**

- **Côté requêtes.** `AuditDeniedQueryMiddleware` sur le `query.bus` audite `PermissionDenied` et `ResourceNotFound` levés par un handler de requête (`denied`).
- **Côté commandes.** `AuditFailureMiddleware` sur le `command.bus` audite les refus et les échecs.
- **Marquage, et format de l'exception qui sort des bus.**
  - Les deux middlewares d'audit **déroulent eux-mêmes `HandlerFailedException`** avant d'envelopper. Ils relancent l'exception métier dans **`Shared\Application\Audit\AlreadyAudited`**, un objet immuable placé à côté d'`AuditTrail`. Il expose deux méthodes :
    - `cause()`, qui donne directement l'exception métier (`BusinessRuleViolated`, `PermissionDenied`…) ;
    - `action(): AuditAction`, l'action de la commande ou de la requête auditée.

    `PublishDomainEventsMiddleware` lit `action()` pour référencer la commande échouée dans `event.handler.failed`, et le test des « trois entrées » le vérifie. Aucun marqueur modifiable n'est posé sur l'exception d'origine.
  - **Ce qui sort de `CommandBus` ou de `QueryBus` pour un refus ou un échec audité est donc toujours `AlreadyAudited`.** `UnwrapsHandlerFailure` reste limité à `HandlerFailedException`, et **aucun bus ne retire l'enveloppe**.
  - Le listener `kernel.exception`, `FrameExceptionRenderer` et `ActionResponder` lisent `cause()`. Ils n'auditent que ce qui n'est **pas** enveloppé, c'est-à-dire les refus du firewall et d'un voter appelé dans un contrôleur. On obtient exactement une entrée par refus.
  - Un test vérifie ce format pour chaque bus.
- **Lectures.** Les GET des frames ne sont pas audités quand ils réussissent.

**Tests**

- **Data provider sur toutes les cases de `TurboFrame`.** On vérifie d'abord qu'il existe **exactement un `FrameView` par case**. Puis, pour chacune :
  - une session authentifiée est exigée ;
  - hors portée, la réponse est une 404, et sans permission une 403, **toujours avec `<turbo-frame id>`** et exactement une entrée `denied` ;
  - `Cache-Control: no-store` et `Vary` sont présents ;
  - sans en-tête `Turbo-Frame`, la réponse est une 303 vers `fallbackRoute()`, dans le même contexte.
- **Actions.**
  - Une requête invalide donne une 422.
  - Une `BusinessRuleViolated` levée par un handler, par exemple `QuotaExceeded`, donne une **422 dans la frame du formulaire**, avec les saisies conservées et exactement une entrée `denied`. Un `PermissionDenied` donne une 403, et ainsi de suite pour chaque ligne de la table.
  - `handle()` lève une `LogicException` **avant tout `dispatch`** dans les deux cas d'incohérence entre `RevealsSecret` et `SecretRevealingResponse`. Aucune entrée `success` n'est alors écrite, et l'ancien lot de codes reste valide.
  - Un POST sans jeton CSRF donne une **403** avec exactement une entrée `csrf.rejected` (`denied`). C'est vrai pour un formulaire, pour un bouton, pour chacune des **sept routes d'authentification** et pour le **logout**. Sur la connexion et le second facteur, le test passe par `CsrfAwareFailureHandler` et vérifie qu'aucune entrée « échec de connexion » n'est écrite en plus.
  - `ConfirmTotp` avec un code faux donne une 422, sans aucun code de secours dans la réponse, avec une seule entrée `failure`, et le TOTP reste `PendingTotp`.
  - Une 422 ne renvoie jamais de mot de passe ni de code.
  - Pour chaque bouton (`ActionButtonType`), un refus métier est rendu dans sa frame avec le statut de la table.
  - Une requête valide avec le stream donne des `replace` sur les frames de la table, ou `remove` pour une frame devenue invisible.
  - Sans en-tête de stream, la réponse est une 303, sauf pour les actions qui affichent un secret.
  - La table de correspondance des refus est couverte par un test unitaire exhaustif.
- **Navigation.**
  - Un rechargement après une pagination affiche la page complète.
  - Une connexion après une expiration survenue pendant une frame revient sur la page.
  - La balise `turbo-cache-control` est présente.
  - Aucun attribut `style=` ne figure dans les templates authentifiés.
- **`frame_state_controller.ts`.** Il passe `make typecheck`. Ses comportements dans le navigateur relèvent de la **vérification manuelle**, et leur test automatisé est un non-objectif de ce step.

## Fichiers

Tous les chemins sont relatifs à `console/`, sauf mention contraire.

- **`composer.json`**, via `make composer c='req …'` :
  - sécurité et 2FA : `symfony/security-bundle`, `scheb/2fa-bundle`, `scheb/2fa-totp`, `scheb/2fa-backup-code`, `scheb/2fa-trusted-device` ;
  - Symfony : `symfony/mailer`, `symfony/rate-limiter`, `symfony/lock`, `symfony/form`, `symfony/validator`, `symfony/translation`, `symfony/clock` ;
  - QR code : `endroid/qr-code` ;
  - en dev : `dama/doctrine-test-bundle`.
- **`config/packages/`** :
  - `security.yaml` : firewall, `access_control` et `argon2id` ;
  - `scheb_2fa.yaml`, et `mailer.yaml` avec `message_bus: false` ;
  - `rate_limiter.yaml` : tous les limiteurs nommés du composant `symfony/rate-limiter`, en `sliding_window`, avec `storage_service: DbalRateLimiterStorage` (connexion dédiée `rate_limiter`, table `rate_limiter_state`) et `lock_factory: lock.factory` ;
  - `lock.yaml` : store `DoctrineDbalPostgreSqlStore` sur la connexion `rate_limiter` ;
  - `framework.yaml` : session PDO (handler construit sur le DSN PDO natif, avec les délais en `options`), cookies, `trusted_proxies` ;
  - `messenger.yaml` : ordre des middlewares commenté, et `doctrine_transaction` retiré d'`event.bus` ;
  - `doctrine.yaml` : types d'id, connexion `rate_limiter` avec son middleware de pilote `SessionTimeoutsDriverMiddleware`, et connexion `owner` réservée à la CLI ;
  - `doctrine_migrations.yaml` : migrations sur la connexion `owner` ;
  - `translation.yaml`.
- **`.env`** :
  - `MAILER_DSN` ;
  - `DATABASE_URL` (rôle `depverify_app`). `DATABASE_MIGRATIONS_URL` n'est **pas** dans `.env*` : elle est dans `.docker/database/owner.env`, ignoré par git, avec un modèle `owner.env.dist` ;
  - `APP_SECRET`, `APP_ENCRYPTION_KEYS` et `APP_HASH_PEPPER`, vides (tous les trois en échec fermé), avec des valeurs de dev dans `.env.dev` et de test dans `.env.test` ;
  - `AUDIT_RETENTION_DAYS=365` ;
  - `SYMFONY_TRUSTED_PROXIES` vide.
- **`compose.prod.yaml`** : `FRANKENPHP_LOOP_MAX=500` sur le service `php` (mode worker en production, décision 30).
- **Docker** :
  - `.docker/database/roles.sh`, idempotent, crée les rôles ;
  - dans `compose.yaml`, le service `database` monte ce script dans `/docker-entrypoint-initdb.d/`, et la variable `DATABASE_URL` du service `php` passe sur `depverify_app`. `DATABASE_MIGRATIONS_URL` n'y figure pas ;
  - `compose.override.yaml` ajoute `mailpit`, avec une **image épinglée par tag et digest**. Le SMTP écoute sur `mailpit:1025` dans le réseau Docker, et l'interface web sur 127.0.0.1:8025. `.env.dev` pose `MAILER_DSN=smtp://mailpit:1025`.
  - **En production**, la procédure d'exploitation impose un TLS obligatoire pour `MAILER_DSN` (`smtps://`, ou STARTTLS non optionnel). Avec la décision 24, la boîte mail compte comme un facteur d'authentification.
- **`Makefile`** :
  - `make mailpit`, `make super-admin`, `make audit-partitions`, `make db-roles` ;
  - seuls `db-migrate`, `db-diff` et `audit-partitions` injectent `DATABASE_MIGRATIONS_URL`, via `docker compose exec -e` et sans valeur dans l'argument ;
  - `qa` inclut désormais `audit` (`composer audit`), puisqu'il n'y a pas de workflow à part.
- **`migrations/2026/`** :
  - `sessions` et `rate_limiter_state` (l'état des limiteurs), avec leurs `GRANT` ;
  - le schéma `audit` et la table `audit.audit_log` : partitions, triggers de ligne et `TRUNCATE`, privilèges par défaut ;
  - les tables Identity, dont `code_verification_attempt`, et les tables Organization.

  Les index partiels et le SQL brut sont relus à la main.
- **Code** : `src/Shared/…`, `src/Audit/…`, `src/Identity/…` et `src/Organization/…`, en suivant les conventions de `CLAUDE.md`.
- **Templates et traductions** : `templates/{identity,organization,audit,email}/…` et `translations/messages.en.yaml`.
- **`tests/Architecture/LayerDependencyTest.php`** :
  - autoriser `Symfony\Component\String` en Domain et `Shared\Application\Contract` entre contextes (`Psr\` est déjà autorisé en Application) ;
  - interdire `Scheb\`, `Symfony\Component\Security` et `Symfony\Component\Mailer` en Domain et en Application.
- **Documentation** :
  - `CLAUDE.md` de la console ;
  - `.github/docs/cadrage.md` : §3, §5, §5ter, §7 et §7bis. On y reporte :
    - les décisions 1 à 26 ;
    - les deux rôles PostgreSQL et le schéma `audit` ;
    - les risques acceptés : décision 24, et audit de l'authentification qui échoue ouvert ;
    - en §3, une ligne de **carte des contextes** : Identity consomme le contrat `FindPendingInvitation` d'Organization, et Organization consomme `AccountDeactivated` / `AccountReactivated` d'Identity. C'est une relation client/fournisseur dans les deux sens, uniquement par des contrats `Shared` ;
  - `.github/docs/design.md` §6 : invitation, mot de passe oublié, ré-authentification et quotas. Et en §5, le motif « frame lazy + placeholder `Skeleton` + état d'erreur avec Retry + mise à jour par Turbo Stream après une action » (décision 31).

## Réutilisation

**Dans la console**

- Les bus `Shared\Application\Bus\*`, les handlers routés par `_instanceof` (`config/services.yaml`) et `UnwrapsHandlerFailure` (`src/Shared/Infrastructure/Bus/`).
- Le pattern `#[AutoconfigureTag]` + `#[AutowireIterator]` de `src/Shared/Application/Health/HealthProbe.php`.
- L'enum `RouteCollection` avec `prefixed()` (`src/Shared/UI/Controller/RouteCollection.php`), déclinée par contexte.
- Les layouts `templates/shared/layout/{auth,app}.html.twig` et la maquette `templates/shared/preview/login.html.twig`, à déplacer.
- Les composants existants `NavUser`, `TeamSwitcher`, `AppSidebar`, `Field*`, `Input`, `Button`, `Card*`, `Dialog*` et `DropdownMenu*`.
- `tests/Shared/Functional/UI/HealthcheckControllerTest.php` comme modèle de `WebTestCase`.

**Dans les autres projets, pour s'en inspirer**

- `Romain-MILLAN-Finance` :
  - `config/packages/security.yaml` : throttling, logout CSRF, `is_fully_authenticated` ;
  - `src/Security/Authorization/AuthorizationDenialLogger.php` ;
  - `src/Message/Command/Organization/Handler/InviteMemberHandler.php`.
- `association-yggame` :
  - `config/packages/scheb_2fa.yaml` ;
  - `src/Common/Security/TwoFactorEnrollmentSubscriber.php`.
- `crazy-game-jam` :
  - `templates/email/layout.html.twig` et `templates/components/email/*` ;
  - `src/Common/Listener/Security/LogLogin{Success,Failure}Listener.php` et `FailureReasonMapper`.

## Étapes

**Commit 1 — « feat: Add the shared kernel and the append-only audit log »**

1. Installer `symfony/clock`, `symfony/rate-limiter`, `symfony/lock` et `dama`. Le port `AttemptThrottle` et son stockage en échec fermé font partie du commit 1.
2. Ajouter le script des deux rôles PostgreSQL, la connexion `owner`, et les migrations exécutées sur cette connexion.
3. Écrire le socle Shared :
   - `RecordsEvents` et `EventRecording` ;
   - les ids et leurs types ;
   - `CurrentActor`, `RequestContext` et `SecretBox` (avec `kid` et échec fermé) ;
   - les formats de jeton et `TokenHasher` ;
   - `AuditTrail`, `AuditEntry` (typé), le port tagué `AuditScopeResolver`, `SelfAuditedCommand` et `PermissionDenied` / `ResourceNotFound` ;
   - l'enum `Permission`, `SlugGenerator` et `SecurityHeadersSubscriber` ;
   - les cinq middlewares maison du `command.bus` (`PublishDomainEvents`, `AuditFailure`, `ResetUnitOfWorkOnFailure`, `LockTimeout`, `AuditSuccess`), dans l'ordre fixé, et le collecteur `ResetInterface` ;
   - `AuditDeniedQueryMiddleware` sur le `query.bus`, `Shared\Application\Audit\AlreadyAudited` (avec `cause()` et `action()`), `Shared\Domain\BusinessRuleViolated`, et le test « format de sortie par bus » ;
   - les tests de concurrence et de délai (55P03, plusieurs connexions) **sortent de `dama`**, avec une désactivation ciblée et un nettoyage explicite des données : chaque connexion doit voir les données committées ;
   - le port `AttemptThrottle` et son adaptateur, le port `ExclusiveSection` et l'adaptateur `LockExclusiveSection`, la connexion `rate_limiter`, `DbalRateLimiterStorage`, `symfony/lock`, `LockTimeoutMiddleware` et `app:rate-limiter:prune`.
4. Écrire la migration `audit_log`, `DbalAuditTrail`, `maintain-partitions` (avec la migration depuis la partition `DEFAULT`), `ListAuditEntries` et le listener des refus du firewall.
5. Écrire les tests :
   - unitaires ;
   - d'intégration : triggers, rôle runtime incapable de `DROP` ou `ALTER`, partitions, `DEFAULT`, échec d'un handler laissant quand même une ligne `failure`, un refus produisant une seule entrée, collecteur vidé après un rollback ;
   - mise à jour du test d'architecture.

   Puis `make qa`.

**Commit 2 — « feat: Add authentication with second factor and account security »**

6. Installer les paquets d'Identity et ajouter Mailpit.
7. Écrire le Domain d'Identity (embeddables, State `SecondFactor`, `EmailLoginCode::verify`), puis l'Application (commandes de vérification sans exception, `ActivateInvitedAccount` lié au jeton, verrou advisory sur le dernier super admin).
8. Écrire l'Infrastructure :
   - `SecurityUser` (`__serialize`, `EquatableInterface`), `UserProvider` et `UserChecker` ;
   - les adaptateurs scheb et le limiteur du 2FA ;
   - le hachage factice ;
   - les sessions et `SessionLifetimeSubscriber` ;
   - la ré-authentification par nom de route ;
   - l'échange de jeton en session ;
   - le subscriber d'audit d'authentification ;
   - `DeferredMailQueue` et les emails d'alerte.
9. Écrire **tout le socle UI de Shared**, utilisé dès Identity :
   - `Shared\UI\Frame`, `FrameView`, `FrameExceptionRenderer` et `ActionFrameMap` ;
   - `ActionResponder`, avec `ActionForm`, `ActionButtonType`, `FrameRefresher`, `CsrfRejection`, la table des refus et les Strategies `ResponseFormat` (`StreamOrRedirect` et `SecretRevealingResponse`) ;
   - `TargetPathSubscriber`, `CspNonce`, `frame_state_controller.ts` et le composant `skeleton` du kit.

   Écrire ensuite la CLI, les écrans d'authentification (avec le CSRF des sept routes) et de sécurité du compte, ainsi que `/admin/users` et sa frame lazy. Supprimer les previews.
10. Écrire les tests (voir Vérification), puis `make qa`.

**Commit 3 — « feat: Add teams, projects, memberships, permissions and quotas »**

11. Écrire le Domain d'Organization (`Quota`, `Team` racine de `TeamMembership` avec `adminEstablished`, `Project` racine de `ProjectMembership` et d'`Environment`, `Invitation`, specifications, `RolePermissions`, resolver pur), avec **un test par case de la table §7bis** (via un data provider) et un test par permission additionnelle.
12. Écrire les handlers avec le verrou d'équipe, la vérification du propriétaire réel, la limite de renvoi des invitations et la consommation de `AccountDeactivated` / `AccountReactivated`. Écrire aussi les voters, le décorateur du resolver, les repositories filtrés et le parcours d'invitation.
13. Écrire les écrans d'Organization et la sidebar, en réutilisant le socle UI de l'étape 9 :
    - les enums `TurboFrame`, les `FrameView` et les tables `ActionFrameMap` d'Organization ;
    - les frames lazy (placeholders `Skeleton`) et leurs endpoints ;
    - les réponses Turbo Stream des actions ;
    - la frame et la page d'audit d'équipe (`/teams/{teamId}/audit`) côté Audit.
14. Écrire les tests, mettre à jour la documentation, puis `make qa`.

Les commits n'ont qu'une ligne de sujet, sans corps ni `Co-Authored-By`. Chacun est créé à la fin de sa sous-étape, puis poussé, et la CI est vérifiée.

## Cas limites

**Codes, 2FA et appareils de confiance**

- Code email expiré, déjà utilisé, ou 5ᵉ échec : le code est invalidé et l'incrément est committé. Au 6ᵉ essai, le code est refusé même s'il est exact. Il faut alors en redemander un, dans la limite de 3 renvois par 15 min.
- TOTP, code de secours ou ré-authentification : au 6ᵉ échec en 15 min, le jeton 2FA est annulé et l'utilisateur repart de la connexion.
- Les opérations suivantes appellent `revokeAll()`, qui révoque toutes les sessions et tous les appareils de confiance : changement ou réinitialisation du mot de passe, réinitialisation du 2FA, désactivation, retrait du super admin, et toute modification du TOTP ou des codes de secours.
- Un compte qui a le TOTP ne peut **jamais** obtenir de code email.
- Le TOTP n'est actif qu'après confirmation (état `PendingTotp`). Un code TOTP rejoué est refusé.

**Connexion et comptes**

- Email inconnu, mauvais mot de passe ou compte désactivé : le message est le même, et le temps de réponse est comparable (hachage factice, emails différés). La raison réelle n'est écrite que dans l'audit.
- Avec `SameSite=Strict`, le premier clic depuis un email arrive sans session. Les pages d'arrivée sont donc publiques et échangent le jeton contre une valeur en session.
- Le retrait du dernier super admin actif, ou de soi-même, est refusé sous verrou advisory, et le refus est audité.
- La CLI agit avec l'acteur `cli`, sans voter. Seule la commande `create-super-admin` existe.

**Invitations et membres**

- Invitation destinée à un autre email que celui de l'utilisateur connecté : refus explicite.
- `ActivateInvitedAccount` sur un compte déjà complet : refus.
- Invitation pour quelqu'un qui est déjà membre : message neutre.
- Invitation de projet pour un membre de l'équipe : pas de `TEAM_GUEST` créé.
- Quota atteint entre l'invitation et son acceptation : l'acceptation est refusée et l'invitation reste en attente.
- Deux acceptations simultanées : le verrou d'équipe et la contrainte d'unicité les départagent, et la seconde acceptation est idempotente.
- Deux `CreateProject` ou deux `InviteMember` simultanés à « quota − 1 » : le verrou d'équipe les sérialise, et la seconde demande est bloquée. Un test d'intégration de concurrence couvre ce cas, ainsi que celui du dernier admin.
- Le dernier `TEAM_ADMIN` actif ne peut être ni retiré ni rétrogradé. S'il est désactivé par le super admin, l'équipe est gérée par le super admin seul.
- Un `PROJECT_ADMIN` qui touche à un rôle d'équipe, ou qui accorde une permission qu'il n'a pas : refus 403.
- Un `TEAM_GUEST` qui n'a plus aucun projet **reste membre** : il apparaît avec un badge « no project » et compte dans le quota. Son retrait est explicite.
- Accès à un objet enfant d'une autre équipe (invitation, environnement, membership) : 404. Un test à deux équipes couvre chaque type d'objet.
- Échec de la cascade de suspension après la désactivation d'un compte : le compte reste désactivé, l'échec est audité, et la commande peut être rejouée depuis l'admin. Le compte désactivé ne peut de toute façon plus se connecter.
- Un même code de secours, ou un même TOTP, soumis deux fois en parallèle : le verrou `User` et `lastAcceptedStep` font qu'un seul passe.
- Après 20 échecs de second facteur en 24 h : le 2FA est bloqué jusqu'à la fin de la fenêtre, et le titulaire est alerté par email.
- Demandes répétées de mot de passe oublié : au-delà de 3 par heure, la réponse reste identique mais aucun email n'est envoyé.

**Quotas, projets et environnements**

- Un quota abaissé sous l'usage actuel ne supprime rien mais bloque les nouvelles créations. La jauge affiche alors plus de 100 %.
- Un projet ou un environnement non vide ne peut pas être supprimé.
- Un slug en collision reçoit un suffixe numérique.
- Un nom d'environnement en double (sans tenir compte de la casse) est refusé.

**Audit**

- Aucun mot de passe, jeton, code, secret ni corps de requête n'entre dans l'audit : c'est garanti par le typage du contexte et vérifié par un test.
- Un succès est écrit dans la transaction : si cette écriture échoue, la commande échoue. Un échec ou un refus est écrit après le rollback.

## Vérification

**Automatique : `make qa`**

`make qa` lance lint, typecheck, php-cs-fixer, PHPStan au niveau max, Rector, PHPUnit, Infection à **100 % de MSI** sur Domain et Application, et `composer audit`.

Tests fonctionnels (`WebTestCase` + `dama`, assertions Mailer, `MockClock`) :

- **Connexion et 2FA** :
  - code email : bon code, code expiré, 6ᵉ essai, renvoi limité ;
  - TOTP, avec un code calculé à partir du secret ;
  - 6ᵉ TOTP faux en 15 min ;
  - code de secours à usage unique ;
  - appareil de confiance valable 30 jours, puis révoqué par un changement de mot de passe.
- **Limites et sessions** : limite au login, inactivité de 30 min et durée totale de 12 h (via `MockClock`), ré-authentification au-delà de 10 min.
- **Redirections** : `_target_path=https://evil` et retour après ré-authentification ne mènent jamais à une URL externe.
- **Mot de passe oublié** : même réponse pour un email inconnu, et email différé.
- **Compte sans `account.login`** : connexion refusée.
- **Session et cache** : la session sérialisée ne contient ni hash ni secret TOTP. Deux requêtes successives dans le même kernel, avec deux acteurs, n'ont aucune permission en commun.
- **Invitations** : nouveau compte, compte existant, mauvais email, invitation expirée, révoquée, quota atteint à l'acceptation, invitation de projet créant un `TEAM_GUEST`, acceptation rejouée (idempotente), jeton absent de l'URL finale, renvoi limité.
- **Garde et portée** : dernier admin, dernier super admin, rang des rôles, extras ○ uniquement. Un `TEAM_GUEST` reçoit 404 sur les autres projets. Le quota bloque aussi le super admin.
- **En-têtes** : CSP, `frame-ancestors 'none'`, `Referrer-Policy` et HSTS sont présents.
- **Emails d'alerte** : chaque cas de la décision 26 envoie son email.

Tests d'intégration :
- **Base de données** : `current_user = depverify_app` et `NOT rolsuper` ; triggers de ligne et de `TRUNCATE` ; `UPDATE`, `DELETE` et `TRUNCATE` directs refusés sur une partition créée après la migration et sur `DEFAULT` ; partitions.
- **Audit et événements** : audit d'un échec malgré le rollback ; refus audité une seule fois ; commande imbriquée en échec (`success` externe, `failure` imbriqué, `event.handler.failed`, aucun email envoyé) ; imbrication sans perte ni double publication d'événement ; jeton absent de l'audit et des logs en cas d'échec d'`InvitationSender` ; un seul `failure` par mauvais code ; `maintain-partitions` avec des lignes dans `DEFAULT`, triggers actifs juste après ; resolver de portée sur une création annulée (`Scope::none()`) ; commande A en échec puis commande B dans la même requête, sans que rien de A ne soit persisté ni publié (EM vidé) ; exception technique d'une commande auto-auditée bien auditée en `failure` ; `event.handler.failed` qui nomme le handler le plus interne ; `DATABASE_MIGRATIONS_URL` absente du kernel web ; événement d'une racine non modifiée bien publié ; aller-retour Doctrine de chaque état (`SecondFactor`, `Credentials`, `AccountStatus`).
- **Concurrence** : sur le quota, sur le dernier admin, sur un même code de secours et sur une double activation de compte.
- **Échec de cascade** : `SuspendMembershipsOfUser` en échec, puis rejoué.

Tests fonctionnels supplémentaires : limite du mot de passe oublié (réponse identique), limite du second facteur sur 24 h avec son email d'alerte, TOTP rejoué refusé, et une sonde `ProjectContentProbe` factice qui bloque la suppression d'un projet.

**Manuelle, sur https://console.depverify.localhost**

1. `make super-admin`, puis connexion avec le code reçu dans Mailpit (http://localhost:8025), en cochant « Trust this device ».
2. Activer le TOTP et garder les codes de secours. Vérifier qu'un email d'alerte est reçu, puis se déconnecter et se reconnecter.
3. Créer une équipe A avec un premier admin, puis accepter l'invitation en navigation privée. Vérifier que l'URL finale ne contient pas le jeton.
4. Connecté en `TEAM_ADMIN` : atteindre le quota de projets, inviter un `TEAM_GUEST` sur un seul projet, et vérifier qu'il ne voit que ce projet (404 sur les autres).
5. Ouvrir `/admin/audit` : tout y est, sans aucun secret. Lancer `make audit-partitions`. Dans Adminer, connecté avec le rôle `depverify_app`, vérifier que `TRUNCATE`, `DELETE` et `DROP` sont refusés sur `audit.audit_log` et sur ses partitions.
6. Vérifier que `/_healthcheck` répond 200.
7. Vérifier le comportement de Turbo :
   - les listes et les jauges s'affichent d'abord en squelette, puis se remplissent ;
   - après une invitation, la liste et la jauge se mettent à jour sans rechargement, et le dialog se ferme ;
   - session expirée (attendre ou supprimer le cookie), puis chargement d'une frame : on arrive sur le login en pleine page, et la connexion ramène à la page parente ;
   - serveur coupé pendant le chargement d'une frame : une alerte « Retry » s'affiche ;
   - un retour arrière ne réaffiche pas les codes de secours.

## Non-objectifs

- Le test automatisé en navigateur de `frame_state_controller.ts` (session expirée, 5xx, erreur réseau). Ces comportements sont couverts par la vérification manuelle.

- Les passkeys, prévues au step 1b.
- La création des comptes « notification seule », la confirmation de leur email, le désabonnement et le quota `maxNotificationOnlyAccounts`.
- La suppression d'équipe en cascade, l'effacement RGPD et l'anonymisation de l'audit.
- L'écran SMTP d'InstanceSettings, la vérification HIBP et le verrouillage de compte.
- **Le TOTP obligatoire pour le super admin**, écarté par la décision 24.
- L'audit des lectures réussies, ainsi que la surveillance du volume d'audit et les alertes sur ses pics.
- L'application des quotas des autres contextes : agents, jetons, canaux et rétention.
- L'API publique, les jetons d'API, le SSO et la traduction française.
- La planification automatique de `maintain-partitions`, qui arrivera avec Scheduler et le worker (la partition `DEFAULT` et les 12 mois créés à l'avance couvrent l'intervalle), et un probe de healthcheck pour le mailer.
- Le passage du bus d'événements en asynchrone. Il imposera de ne plus transporter de jeton en clair dans les événements, ce qui est documenté.
- La preuve d'altération du journal d'audit par chaînage des entrées (hachage). Le journal est non modifiable par l'application, pas infalsifiable par le rôle propriétaire.

<!-- validation-gourous -->
## Validation des gourous

| Tour | Rév. | Hash | Gourou | Points majeurs | Traitement | Verdict |
|---|---|---|---|---|---|---|
| 1 | 1 | 49f59f8b | dev | Audit et transaction contradictoires ; compteur d'essais du code email perdu au rollback ; état partagé en mode worker (cache du resolver, collecteur d'événements) ; secret TOTP sérialisé dans la session ; port Mailer qui traverse les contextes ; métadonnées d'audit portées par la commande et double audit d'un refus ; `User` trop gros et nullable ; quotas nullables et non verrouillés ; `MembershipGuard` fourre-tout ; test d'architecture (String, Slugger) ; formats de jeton ; parcours d'invitation sans garantie | Tout intégré en rév. 2 : middlewares `AuditFailure`, `PublishDomainEvents`, `doctrine_transaction` puis `AuditSuccess` ; `VerifyEmailLoginCode` sans exception et `EmailLoginCode::verify` ; resolver pur et décorateur `ResetInterface` ; `__serialize` minimal et `EquatableInterface` ; ports fins par contexte et emails envoyés après le commit ; `AuditScopeResolver`, ids générés par l'UI et `PermissionDenied` audité une seule fois ; embeddables et State `SecondFactor` ; VO `Quota` et verrou d'équipe ; specifications et `canAssign` ; liste blanche String et port `SlugGenerator` ; stratégie de formats ; `ActivateInvitedAccount` lié au jeton et orchestrateur nommé. ⚪ intégrés : trait `EventRecording`, séparation `CurrentActor` / `RequestContext`, `isSuperAdmin` dans le Domain, `AuditEntry` composée, `Permission` assumé ouvert, `PermissionGrant` dans la même transaction, ré-authentification limitée à l'UI documentée | OBJECTIONS |
| 1 | 1 | 49f59f8b | ddd | Pas de frontière de cohérence (dernier admin, quotas) ; dernier super admin sans verrou ; Mailer d'Identity utilisé par Organization ; email envoyé avant le commit et infrastructure d'événements sans événement ; désactivation invisible pour Organization (« membre actif » non défini) ; invitation sans orchestrateur ni lien au jeton ; ordre de l'audit et double audit | Tout intégré : `Team` verrouillée comme frontière et test de concurrence ; `pg_advisory_xact_lock` ; `InvitationSender` dans Organization ; `InvitationIssued` et les événements d'Identity, emails différés ; `UserDeactivated` / `UserReactivated` consommés, membership `suspended`, « membre actif » défini ; `InvitationController` orchestrateur, acceptation idempotente, état « activé sans membership » assumé ; ordre des middlewares et `PermissionDenied`. ⚪ intégrés : méthodes métier sur `Invitation`, `User` et `Team` ; expiration calculée et révocation automatique de l'invitation expirée ; appartenance de `BackupCode`, `EmailLoginCode` et `PasswordResetRequest` ; `isSuperAdmin` à la place de `roles` ; `PermissionGrant` comme historique métier et audit comme trace de sécurité ; `TEAM_GUEST` sans projet conservé | OBJECTIONS |
| 1 | 1 | 49f59f8b | security | 2FA sans limite ; cache du resolver en mode worker ; audit d'échec perdu au rollback ; journal modifiable par le rôle propriétaire ; BOLA sur les objets enfants ; 404 ou 403 non tranché ; `ActivateInvitedAccount` sans invariant ; trusted proxies ; jetons dans l'URL et en-têtes absents ; redirection ouverte ; temps de réponse qui révèle les comptes ; pas d'alerte sur les changements sensibles ; TOTP du super admin ; formats de code ; état 2FA en cours ; `MockClock` sans effet sur le GC PDO ; contexte d'audit ; abus du renvoi d'invitation ; `composer audit` hors de `qa` ; clé de chiffrement en échec fermé | Intégré : limiteur du 2FA ; décorateur `ResetInterface` ; audit d'échec hors transaction ; deux rôles PostgreSQL (arbitrage, décision 25) ; vérification sur le propriétaire réel et test à deux équipes ; 404 hors portée et 403 visible ; `ActivateInvitedAccount` revérifie le jeton et verrouille ; `SYMFONY_TRUSTED_PROXIES` vide par défaut ; échange du jeton en session, `Referrer-Policy` et en-têtes ; retour par nom de route ; hachage factice et emails différés ; emails d'alerte (décision 26) ; formats `NumericCode` et `BackupCodeFormat` ; `IS_AUTHENTICATED_2FA_IN_PROGRESS` ; `SessionLifetimeSubscriber` sur `ClockInterface` ; contexte typé et borné ; limite de renvoi ; `composer audit` dans `qa` ; `kid` et échec fermé. ⚪ intégrés : AAD avec l'id, `authVersion` incrémenté au retrait du super admin, migration depuis la partition `DEFAULT`, volume d'audit documenté, mot de passe comparé sans la casse, formulaires vers des DTO, `--password-file`. **TOTP obligatoire pour le super admin : objection close par arbitrage (décision 24, risque accepté).** Ligne « Ouvrir dans Chrome » : c'est la règle `plan-html-link.md` de l'utilisateur, une donnée attendue | OBJECTIONS |
| 2 | 2 | 99135e9d | dev | Tour 1 entièrement validé. Nouveaux points : un handler d'événement en échec après le commit falsifie le journal ; le collecteur `onFlush` perd les événements d'une racine non modifiée ; `GetCodeVerificationOutcome` n'a rien à lire ; un embeddable Doctrine polymorphe n'existe pas ; le TOTP contourne le bus et son rejeu n'est pas modélisé ; on ne peut pas verrouiller une ligne d'email qui n'existe pas ; la propriété de `ProjectMembership` est ambiguë | Intégré en rév. 3 : `PublishDomainEvents` placé le plus à l'extérieur, échec d'un handler d'événement audité sous `event.handler.failed` sans requalifier la commande ; collecte sur toute l'identity map et vidage en cas d'exception ; registre `CodeVerificationAttempt` ; embeddables avec `kind` et factory, plus un test aller-retour par état ; commande `VerifyTotp` et `lastAcceptedStep` ; verrou advisory sur l'email ; carte des agrégats (`Team` → `TeamMembership`, `Project` → `ProjectMembership` et `Environment`). ⚪ intégrés : `adminEstablished`, exceptions à la règle des 4 attributs consignées, `invalidateBackupCode` vide et documenté, secret TOTP injecté par `refreshUser`, `console.terminate`, `doctrine_open_transaction_logger` conservé, écart à la séparation commande/requête documenté, `Psr\` déjà autorisé | OBJECTIONS |
| 2 | 2 | 99135e9d | ddd | Tour 1 entièrement validé. Nouveaux points : la cascade de désactivation n'a ni transaction, ni verrou, ni audit ; l'usage unique des codes n'est pas protégé contre la concurrence ; « projet vide » n'est pas défini et dépend de contextes futurs ; un verrou d'équipe qui couvre plusieurs agrégats sans que ce soit assumé | Intégré : un handler d'événement qui traduit le fait en commande (`SuspendMembershipsOfUser` / `RestoreMembershipsOfUser`), idempotente, verrous pris dans l'ordre des `teamId`, auditée, rejouable depuis l'admin, avec un test d'échec ; `UserRepository::lockById()` et un test de concurrence ; « vide » = aucun environnement, invitations révoquées, port `ProjectContentProbe` ; carte des agrégats et écart consigné dans le `CLAUDE.md`. ⚪ intégrés : réactivation au-delà du quota alignée sur le cas du quota abaissé, carte des contextes en §3, `UpdateDefaultQuotas` sans effet sur les équipes existantes | OBJECTIONS |
| 2 | 2 | 99135e9d | security | Tour 1 validé. Décision 24 close, désaccord maintenu en ⚪. Nouveaux points : `compose.yaml` injecte l'URL du superutilisateur et le script d'init ne tourne que sur un volume neuf ; les privilèges par défaut sont hérités par les partitions et `TRUNCATE` contourne les triggers ; mot de passe oublié sans limite ; 2FA sans plafond cumulé ni alerte au titulaire | Intégré : `DATABASE_URL` sur `depverify_app` dans `compose.yaml`, script de rôles idempotent et `make db-roles`, test `NOT rolsuper` ; schéma `audit` dédié avec ses privilèges par défaut, `GRANT` explicite par partition, trigger `BEFORE TRUNCATE`, test sur une partition créée plus tard ; limiteur du mot de passe oublié (3 par heure par email, 20 par heure par IP, réponse identique) ; limiteur de 20 échecs par 24 h et email d'alerte au titulaire. ⚪ intégrés : ré-authentification par mot de passe plus second facteur ; identifiants du propriétaire réservés à la CLI ; table `cache_items` migrée ; audit de l'authentification qui échoue ouvert consigné comme risque accepté ; rotation du superutilisateur ; `X-Request-Id` entrant ignoré | OBJECTIONS |
| 3 | 3 | 354b527e | dev | Tour 2 validé. Nouveau point : `event.bus` a son propre `doctrine_transaction`, donc la commande de cascade est imbriquée (le `failure` est effacé, les emails partent pour un effet annulé). ⚪ : réentrance du collecteur, double nature de `UserDeactivated` | Intégré en rév. 4 : `doctrine_transaction` retiré d'`event.bus` et commenté, test d'une cascade en échec ; collecteur vidé avant publication et test d'imbrication ; traducteur `PublishAccountIntegrationEvents` vers `AccountDeactivated` / `AccountReactivated` | OBJECTIONS |
| 3 | 3 | 354b527e | ddd | Tour 2 validé. Nouveaux points : le décompte d'audit d'une réaction en échec se contredit (3 entrées) ; `AuditScopeResolver` sans contexte propriétaire, qui casserait les frontières et ne verrait pas les créations ; commandes sans méthode du Domain (risque d'anémie). ⚪ : index du code email, traduction des événements d'intégration, vocabulaire `admit` / `addMember`, `CodeVerificationAttempt` dans `User`, Re-sync | Intégré : trois entrées assumées et testées, `event.handler.failed` référence la commande échouée ; port tagué `AuditScopeResolver` dans Shared, implémenté par chaque contexte via l'identity map, `Scope::none()` et un test ; constructeurs nommés et méthodes listés pour `User`, `Team`, `Project` et `Invitation`, règle « aucun setter ». ⚪ intégrés : `consumedAt`, `consumedByAttemptId` et `invalidatedAt` avec un index partiel adapté ; traducteur nommé ; `admit` sur les deux racines ; `CodeVerificationAttempt` hors de l'agrégat ; Re-sync qui lit `GetUserProfile` | OBJECTIONS |
| 3 | 3 | 354b527e | security | Tour 2 validé. Décision 24 close, désaccord maintenu en ⚪. Nouveaux points : commande imbriquée dans la transaction d'`event.bus` ; mauvais codes audités en `success` ; jeton en clair qui fuit dans l'audit ou les logs lors d'un échec de handler ; déplacement depuis `DEFAULT` face aux triggers. ⚪ : mailer sur le bus, `no-store`, HMAC des codes, coquille « middleware 1 », permission des commandes de cascade, resolver périmé | Intégré : transaction retirée d'`event.bus` ; `SelfAuditedCommand`, dont le résultat est lu dans `CodeVerificationAttempt`, et test d'un seul `failure` ; FQCN uniquement dans l'audit et les logs, test sans jeton ; séquence `LOCK` / `DETACH` / `DISABLE TRIGGER USER` / `ENABLE` / `ATTACH` sous le rôle propriétaire, avec un test. ⚪ intégrés : `message_bus: false`, `Cache-Control: no-store`, HMAC avec `APP_HASH_PEPPER`, coquille corrigée (n° 2), acteur `system` et `instance.users.manage` pour Re-sync, resolver vidé après chaque commande d'Organization | OBJECTIONS |
| 4 | 4 | 929ad582 | dev | Tours précédents validés. Nouveau point : après un rollback, l'identity map garde les mutations annulées et les événements non publiés, qui peuvent ressortir au flush suivant. ⚪ : contradiction sur le contexte de `event.handler.failed` ; handler enveloppé deux fois ; règle « traduire en commande » trop absolue ; `SelfAuditedCommand` sur exception technique ; règle des 4 attributs ; SRP du nettoyage des essais | Intégré en rév. 5 : `EntityManager::clear()` / `resetManager()` et purge des événements dans `AuditFailureMiddleware`, consignés dans les principes, avec le test A échoue puis B. ⚪ intégrés : `AuditAction` dans la liste blanche ; handler le plus interne via `UnwrapsHandlerFailure` ; règle reformulée (commande, email différé ou événement d'intégration) ; seul `AuditSuccess` ignore les commandes auto-auditées ; règle générale des 4 attributs avec `InvitationTarget` / `IssuedToken` et écarts consignés. Nettoyage des essais : accepté tel quel, comme le gourou l'admet | OBJECTIONS |
| 4 | 4 | 929ad582 | ddd | Tours précédents validés. ⚪ : méthodes du Domain manquantes (suspend/restore, extras, `isProduction`, quotas par défaut) ; `KeepsATeamAdmin` hors de la racine ; mécanisme de suppression d'un projet ; événement de `reissue` | ⚪ intégrés en rév. 5 : méthodes complémentaires sur `Team`, `Project` et `InstanceSettings`, avec `suspendMember` exempté ; `KeepsATeamAdmin` appliqué par `Team::changeRole` / `removeMember` ; le handler interroge les sondes, appelle `delete()`, puis `Invitation::revoke()` sous verrou ; `InvitationReissued` | APPROUVÉ |
| 4 | 4 | 929ad582 | security | Tours précédents validés. Décision 24 close, désaccord maintenu en ⚪. Nouveau point : `DATABASE_MIGRATIONS_URL` est dans `.env`, donc chargée par chaque worker web. ⚪ : commande auto-auditée en exception technique non auditée | Intégré : variable sortie de tout `.env*`, placée dans `.docker/database/owner.env` (gitignoré, non monté dans `php`), injectée par le `Makefile`, avec `env(default::…)` dans Doctrine et un test d'absence dans le kernel web. ⚪ intégré : `AuditFailure` couvre les commandes auto-auditées, raison `technical` | OBJECTIONS |
| 5 | 5 | 570fbe3a | dev | Tous les tours précédents validés. ⚪ : ordre purge/`clear()` ; SRP de `AuditFailureMiddleware` ; LSP des états `SecondFactor` ; entités détachées au rendu après une cascade en échec | ⚪ intégrés en rév. 6 : `ResetUnitOfWorkOnFailureMiddleware` dédié (portée, puis purge, puis `clear()`) ; transitions invalides via `InvalidSecondFactorTransition`, testées par couple état/opération ; l'UI relit ses données après le `dispatch`, avec un test | APPROUVÉ |
| 5 | 5 | 570fbe3a | ddd | Tous les tours précédents validés. ⚪ : SRP du middleware d'échec ; portée à résoudre avant `clear()`, via `ManagerRegistry` ; `InvitationReissued` absent des événements ; formulation de `KeepsATeamAdmin` ; lignes vides Markdown | ⚪ intégrés : middleware dédié ; portée résolue avant le nettoyage et jointe à l'exception (`AuditScopeStamp`), services ORM via `ManagerRegistry` ; `InvitationReissued` listé ; exception à la suspension écrite dans la specification ; lignes vides ajoutées | APPROUVÉ |
| 5 | 5 | 570fbe3a | security | Tours précédents validés. Décision 24 close, désaccord maintenu en ⚪. Nouveaux points : CSRF limité au login et au logout ; `APP_SECRET`, qui signe le cookie d'appareil de confiance, hors de l'échec fermé ; privilège propriétaire injecté dans `super-admin`. ⚪ : régénération de l'id de session, mot « inaltérable », pepper sans `kid`, recalcul de l'acteur après `clear()` | Intégré : CSRF sur toute requête qui modifie l'état (Form, ou jeton par action), aucun `GET` qui modifie l'état, test 403 sans jeton ; `APP_SECRET` vide dans `.env`, refusé au démarrage s'il fait moins de 32 octets, rotation documentée ; injection limitée à `db-migrate`, `db-diff` et `audit-partitions`, sans valeur dans `argv`. ⚪ intégrés : `migrate(true)` après le 2FA et la ré-authentification, avec un test ; « non modifiable par l'application » et chaînage des entrées en non-objectif ; pepper au format `kid` ; acteur et permissions de B recalculés dans le test A puis B | OBJECTIONS |
| 6 | 6 | 473ff656 | dev | Tous les tours validés. ⚪ seulement : un stamp se pose sur l'enveloppe, pas sur l'exception ; SRP résiduel (résolution de portée dans le middleware de reset) ; `EventHandlerFailureReporter` ; événements limités aux ids et aux scalaires | Notes d'implémentation, ci-dessous | APPROUVÉ |
| 6 | 6 | 473ff656 | ddd | Tous les tours validés. ⚪ seulement : matrice des états de `SecondFactor` (`reset` total et idempotent) ; mécanisme de `AuditScopeStamp` ; « trois middlewares » au lieu de quatre, et test « A échoue puis B » à l'étape 5 | Notes d'implémentation, ci-dessous | APPROUVÉ |
| 6 | 6 | 473ff656 | security | Tous les tours validés. Décision 24 : désaccord maintenu en ⚪ (bandeau « TOTP recommandé » suggéré). ⚪ : routes publiques de la suite du parcours (`/invitations/pending`, `/password/reset/new`) absentes de `access_control` ; jeton présent dans le log d'accès de Caddy au premier `GET` | Notes d'implémentation, ci-dessous | APPROUVÉ |

### Notes d'implémentation (⚪ du tour 6, hors contenu approuvé)

Ces remarques ne changent pas l'approche. Elles seront appliquées pendant l'implémentation.

1. **`AuditScopeStamp`.** `ResetUnitOfWorkOnFailureMiddleware` reconstruit `HandlerFailedException($envelope->with($stamp), $exceptions)`, et enveloppe de la même façon une exception brute levée au `flush` ou au commit. L'UI retrouve `PermissionDenied` / `ResourceNotFound` via `UnwrapsHandlerFailure`. La résolution de portée peut être isolée dans `ResolveAuditScopeOnFailureMiddleware` (2 ter, juste avant le reset).
2. **Rapport d'échec.** `PublishDomainEventsMiddleware` délègue à un `EventHandlerFailureReporter`, qui filtre les champs et se teste seul.
3. **Contenu des événements.** Ils ne portent que des ids et des scalaires, plus le jeton en mémoire pour `InvitationIssued` / `InvitationReissued`. Un test d'architecture le vérifie.
4. **Matrice de `SecondFactor`.** `reset` (et `ResetSecondFactor`) est total et idempotent dans tous les états. `disableTotp` sur `PendingTotp` abandonne l'enrôlement. Les autres transitions hors état lèvent `InvalidSecondFactorTransition`. La table de tests liste chaque cas « no-op » ou « exception ».
5. **Étapes du commit 1.** Il y a « quatre middlewares », plus le reset. Le test « A échoue puis B » fait partie de l'étape 5.
6. **Routes publiques de `access_control`**, déclarées une par une :
   - `GET /invitations/{token}` ;
   - `GET|POST /invitations/pending` (activation) ;
   - `GET /password/reset/{token}` ;
   - `GET|POST /password/reset/new`.

   `POST /invitations/accept` (`IS_AUTHENTICATED_FULLY`) passe avant toute règle plus large. Un test fonctionnel couvre le parcours sans session.
7. **Log d'accès de Caddy.** Un filtre de format `regexp` masque le segment du jeton dans `request>uri` pour `/invitations/` et `/password/reset/`. Un test, ou une vérification manuelle des logs, s'assure que le jeton n'y apparaît pas.
8. **Bandeau « TOTP recommandé »** affiché sur le compte d'un super admin sans TOTP, pour compenser la décision 24 sans la remettre en cause.

**Unanimité au tour 6, révision 6, hash `473ff656`.** Ce que chaque gourou a apporté :
- **dev** : l'ordre des middlewares d'audit, le compteur d'essais sans rollback, l'état en mode worker, la session sans secret, le State persisté et ses transitions, la remise à zéro de l'unité de travail ;
- **ddd** : `Team` comme frontière de cohérence, la carte des agrégats, les cascades traduites en commandes idempotentes, le traducteur d'intégration, le resolver de portée par contexte, des méthodes du Domain sans setter ;
- **security** : les limiteurs (2FA, mot de passe oublié, renvois), deux rôles PostgreSQL avec un schéma `audit` étanche, le BOLA, l'anti-énumération, le CSRF généralisé, les secrets en échec fermé, les identifiants du propriétaire hors du web, les alertes au titulaire.

**Présentation de la révision 6 refusée par l'utilisateur.** Retours : « en local, utilise Mailpit » ; « utilise le composant Symfony rate-limiter » pour les limitations ; « mets les sessions en BDD ». Ils sont consignés dans les Décisions prises 27 à 29 (révision 7), et tout le texte concerné est harmonisé. Le contenu approuvé a changé : un tour complet suit.

**Question de l'utilisateur pendant le tour 7** : « J'aimerais en prod pouvoir utiliser le worker mode de FrankenPHP, possible ? ». Elle est consignée en décision 30 (révision 8) : mode worker confirmé en production, `FRANKENPHP_LOOP_MAX=500`, test dans un vrai worker, interdiction des propriétés `static` mutables. Le tour 7, lancé sur la révision 7, devient caduc. Ses points de fond seront repris, puis un tour complet sera relancé sur la révision 8.
| 7 | 7 | 9cca55f4 | dev | Rapport rendu caduc par la révision 8. Ses points restent valables pour la suite : `RateLimiterFactory` dans des handlers d'Application, ce qui viole la liste blanche ; limiteur annulé par le rollback ; limiteurs sans verrou entre workers. ⚪ : « premier blocage », sessions PDO non testées, formulation de `mock_file` | Intégré en rév. 9 : port `AttemptThrottle`, avec l'adaptateur `SymfonyRateLimiterThrottle` en Infrastructure ; connexion dédiée `rate_limiter` en autocommit, avec un test de rollback ; `symfony/lock` sur un store PostgreSQL et `lock_factory`, avec un test de concurrence. ⚪ intégrés : `justExhausted` et `SecondFactorThrottled` ; test d'intégration du vrai `PdoSessionHandler` ; « aucun handler de fichiers hors test » | (caduc) OBJECTIONS |
| 7 | 7 | 9cca55f4 | ddd | Rapport caduc. ⚪ : sessions PDO et frontière transactionnelle (DSN, `LOCK_ADVISORY`, `GRANT` UPDATE/DELETE) ; consommation des limiteurs avant le `dispatch` ou via un port ; « premier blocage » nommé ; notes 1, 4 et 5 du tour 6 non reprises dans le texte | Intégré : `PdoSessionHandler` construit sur un DSN et jamais sur `getNativeConnection()`, `LOCK_ADVISORY`, `GRANT` complets ; port `AttemptThrottle` et audit `throttle.*` ; `SecondFactorThrottled` ; « quatre middlewares » et matrice `SecondFactor` avec ses cas idempotents désormais dans le texte | (caduc) APPROUVÉ |
| 7 | 7 | 9cca55f4 | security | Rapport caduc. Décision 24 : désaccord maintenu en ⚪. 🟡 : limiteurs non atomiques (pas de `symfony/lock`) ; limiteurs en échec ouvert si leur stockage casse ; jetons en clair dans la table `sessions`. ⚪ : `__Host-` et `use_strict_mode`, clés des limiteurs en clair, purge de `cache_items`, TLS SMTP en production, image Mailpit non épinglée | Intégré : `symfony/lock` et un test de N essais parallèles ; adaptateur en échec fermé (`throttle.storage_failed`), pool dédié distinct de `cache.app`, test sur le vrai pool ; la session ne contient plus que l'id de l'invitation ou de la demande de réinitialisation, et `sess_id` brut est consigné comme risque accepté, avec `gc_probability` / `gc_divisor` fixés. ⚪ intégrés : cookie `__Host-depverify_session` et `use_strict_mode` ; clés HMAC ; `make cache-prune` ; TLS obligatoire en production ; Mailpit épinglé par tag et digest ; notes 6 et 7 du tour 6 (routes publiques, filtre Caddy) désormais dans le texte | (caduc) OBJECTIONS |
| 8 | 9 | 39d251ee | dev | Tour 7 validé. 🟡 : le lieu de consommation du limiteur du 2FA se contredit (handler ou adaptateur), écart entre « échecs » et « essais », pas de `peek`. ⚪ : origine de `SecondFactorThrottled`, échec fermé hors de `login_throttling`, `rate-limiter` et `lock` installés trop tard, test « même worker » non déterministe, connexions hors bus, `LOOP_MAX` déjà par défaut, chaîne brute dans `consume` | Intégré en rév. 10 : consommation dans les handlers `Verify*` / `UseBackupCode` sous le verrou `User`, comptage des **échecs** (décision 6), `peek()` ajouté au port, texte aligné. ⚪ intégrés : `User::noteSecondFactorThrottled`, décorateur `FailClosedRateLimiterStorage` sur `StorageInterface` qui couvre aussi `login_throttling`, installation à l'étape 1, `num 1` en CI, un seul nouvel essai puis échec fermé hors bus, `LOOP_MAX` signalé comme valeur par défaut, VO `ThrottleSubject` | OBJECTIONS |
| 8 | 9 | 39d251ee | ddd | Tour 7 validé. 🟡 : `SecondFactorThrottled` sans émetteur, et lieu de consommation contradictoire. ⚪ : audit d'une commande limitée (fausse entrée `success`), ordre des contrôles dans `ResendInvitation`, connexion `rate_limiter` en mode worker | Intégré : `User::noteSecondFactorThrottled(until, now)` appelé par le handler sous verrou et ajouté à la liste des événements, avec un test « un seul email » ; consommation dans les handlers. ⚪ intégrés : exception `Throttled` auditée une seule fois en `denied` / `throttled` ; ordre chargement, permission, puis limiteur ; nouvel essai après reconnexion | OBJECTIONS |
| 8 | 9 | 39d251ee | security | Tour 7 validé. Décision 24 : désaccord maintenu en ⚪. 🟡 : `login_throttling` échappe à l'échec fermé. ⚪ : rotation du pepper qui remet les fenêtres à zéro, DoS ciblé de 24 h sur le 2FA, `max_connections`, cookie `trusted_device` sans `__Host-` | Intégré : décorateur `FailClosedRateLimiterStorage` pour tous les limiteurs, y compris `login_throttling`, avec un test « stockage indisponible → login refusé et audité ». ⚪ intégrés : clé courante seulement et documentation de la rotation ; DoS de 24 h consigné comme risque accepté, et l'email d'alerte invite à changer de mot de passe ; dimensionnement de `max_connections` ; cookie `__Host-depverify_trusted` | OBJECTIONS |
| 9 | 10 | edc568ff | dev | Tour 8 validé. 🟡 : `Throttled` est à la fois un résultat (L450) et une exception (L517), et il manque dans les résultats de `CodeVerificationAttempt`. ⚪ : algorithme copié dans trois handlers, libellé du test de concurrence (essais au lieu d'échecs), clé IP non atomique entre comptes | Intégré en rév. 11 : `Throttled` est un **résultat** pour les trois commandes auto-auditées (ajouté à l'enum, une seule entrée `denied` / `throttled`, lisible par `GetCodeVerificationOutcome`), et l'exception est réservée aux commandes ordinaires. ⚪ intégrés : service `SecondFactorAttempt` avec une Strategy `CodeCheck` par facteur ; test reformulé (« au plus 5 `Rejected` évalués ») ; verrou sur la clé IP pendant toute la séquence | OBJECTIONS |
| 9 | 10 | edc568ff | ddd | Tours précédents validés. ⚪ : les deux formes de `Throttled`, `noteSecondFactorThrottled` sans changement d'état, double audit de `storage_failed` sur le bus, atomicité de la clé IP | ⚪ intégrés : `Throttled` en résultat ou en exception selon le type de commande ; fait sans changement d'état consigné dans le `CLAUDE.md`, avec un test « racine non modifiée » ; une seule entrée `failure` / `throttle.storage_failed` sur le bus, et une entrée dédiée seulement pour le firewall ; verrou sur la clé IP | APPROUVÉ |
| 9 | 10 | edc568ff | security | Tours précédents validés. Décision 24 : désaccord maintenu en ⚪. 🟡 : `peek` = `consume(0)` renvoie toujours `isAccepted() === true` ; `FailClosedRateLimiterStorage` ne voit aucune panne (le pool avale les erreurs, `CacheStorage::save` est `void`, `peek` n'écrit rien). ⚪ : atomicité de la clé IP, `login_throttling` avec un stockage maison, blocage NAT de 15 min, lien Chrome | Intégré : `peek` calcule `getRemainingTokens() > 0`, avec un test unitaire sur un vrai `SlidingWindowLimiter` ; le pool de cache et son décorateur sont remplacés par **`DbalRateLimiterStorage`** sur la table `rate_limiter_state` (exceptions DBAL remontées, un seul nouvel essai, `allowed_classes`, test « connexion coupée → `peek` lève ») ; `make rate-limiter-prune`. ⚪ intégrés : verrou sur la clé IP ; service `LoginRateLimiter` composé des factories ; risque NAT accepté et consigné. Lien Chrome : donnée attendue | OBJECTIONS |
| 10 | 11 | 71f5e664 | dev | Tour 9 validé. 🟡 : `SecondFactorAttempt` (Application) utilise `Symfony\Component\Lock`, interdit par la liste blanche. ⚪ : `Throttled` absent de L321, phrase cassée en L422, collision entre clés de verrou | Intégré en rév. 12 : port `ExclusiveSection::run(ThrottleSubject, callable)`, adaptateur `LockExclusiveSection` en Infrastructure, ordre des verrous (`User`, puis IP), verrou advisory sur `rate_limiter` hors transaction. ⚪ intégrés : table de correspondance complétée, phrase corrigée, espace de nommage `2fa-ip:` + HMAC | OBJECTIONS |
| 10 | 11 | 71f5e664 | ddd | Tours précédents validés. ⚪ : L321 non alignée, `CodeCheck` doit déléguer à l'agrégat, phrase cassée en L422 | ⚪ intégrés : correspondance `Throttled` → `denied` / `throttled` ; chaque Strategy appelle uniquement la méthode de `User` et ne lit aucun hash ; phrase corrigée | APPROUVÉ |
| 10 | 11 | 71f5e664 | security | Tours précédents validés, `peek` et `DbalRateLimiterStorage` confirmés dans les sources. Décision 24 : désaccord maintenu en ⚪. 🟡 : `reset()` de `LoginRateLimiter` (hérité d'`AbstractRequestRateLimiter`) remet aussi à zéro le limiteur par IP à chaque connexion réussie. ⚪ : clés du login en clair dans `state`, verrous sans délai d'attente, lignes « Chrome » et « Co-Authored-By » signalées | Intégré : `reset(Request)` surchargé pour ne réinitialiser que compte + IP, avec un test (49 échecs, une connexion réussie, tentative suivante refusée). ⚪ intégrés : clés hachées avant la création du limiteur, avec un test sur `id` et `state` ; `lock_timeout` de 5 s sur les transactions de commande et délai de 2 s sur la section exclusive, en échec fermé. Les lignes « Chrome » et « Co-Authored-By » sont des règles de l'utilisateur, donc des données attendues | OBJECTIONS |
| 11 | 12 | 1c26e993 | dev | Tour 10 validé. 🟡 : `SET LOCAL lock_timeout` posé par un listener de connexion, donc hors transaction et sans effet. ⚪ : délai de 2 s sans mécanisme (l'API Lock n'en a pas), `lock.dsn` qui risque d'ouvrir une 4ᵉ connexion, `ExclusiveSection` absent des Étapes, nommage | Intégré en rév. 13 : `LockTimeoutMiddleware` placé juste à l'intérieur de `doctrine_transaction`, avec un test 55P03. ⚪ intégrés : boucle `acquire(false)` avec backoff jusqu'à une échéance calculée par `ClockInterface`, et un test en moins de 3 s ; store `DoctrineDbalPostgreSqlStore` sur la connexion `rate_limiter` elle-même ; port et adaptateur ajoutés à l'étape 3. Nommage : accepté tel quel (usage limité au 2FA) | OBJECTIONS |
| 11 | 12 | 1c26e993 | ddd | Tours précédents validés. 🟡 : `SET LOCAL` hors transaction (même constat que le gourou dev). ⚪ : mécanisme du délai de 2 s, `Throttled` utilisé pour une contention, nommage du port | Intégré : middleware placé après le `BEGIN`, avec un test. ⚪ intégrés : boucle bornée ; raison d'audit `lock_contention`, distincte de `throttled` pour un résultat utilisateur identique. Nommage : accepté | OBJECTIONS |
| 11 | 12 | 1c26e993 | security | Tours précédents validés, et `reset()` de `LoginRateLimiter` vérifié. Décision 24 : désaccord maintenu en ⚪. ⚪ : borne de 2 s non garantie par la librairie, registre `static` de `PostgreSqlStore` après une reconnexion | ⚪ intégrés : boucle `acquire(false)` et test ; libération dans `finally`, aucune nouvelle tentative après reconnexion dans une section exclusive (échec fermé), règle `static` limitée au code du projet | APPROUVÉ |
| 12 | 13 | 4ab5c3ee | dev | Tour 11 validé. 🟡 : le verrou interne du limiteur (`acquire(true)` → `pg_advisory_lock`) n'a pas de borne sur la connexion `rate_limiter` en autocommit, où le `SET LOCAL` du middleware ne s'applique pas. ⚪ : `sleep()` non porté par le port PSR, tests de concurrence sous `dama`, `mailer.yaml` en double | Intégré en rév. 14 : `lock_timeout` de 2 s et `statement_timeout` de 5 s posés **au niveau de la session** sur les connexions `rate_limiter` et sessions (options du DSN), 55P03 / 57014 traduits en échec fermé, et un test « login refusé en moins de 3 s ». ⚪ intégrés : `Symfony\Component\Clock\ClockInterface::sleep()` dans l'adaptateur ; tests de concurrence sortis de `dama` ; `mailer.yaml` fusionné | OBJECTIONS |
| 12 | 13 | 4ab5c3ee | ddd | Tour 11 validé. ⚪ : décompte des middlewares maison périmé (cinq et non quatre) ; lignes « Chrome » et « Co-Authored-By » signalées comme données | ⚪ intégré : « cinq middlewares maison » à l'étape 3 | APPROUVÉ |
| 12 | 13 | 4ab5c3ee | security | Tour 11 validé. Décision 24 : désaccord maintenu en ⚪. ⚪ : le nouvel essai de `DbalRateLimiterStorage` après reconnexion casse les verrous advisory de la même connexion ; attentes sans borne sur les connexions hors bus | ⚪ intégrés : aucun nouvel essai sur les connexions qui portent des verrous (`rate_limiter`, sessions), échec fermé direct, avec un test « coupure pendant `ExclusiveSection` → le code n'est jamais évalué » ; délais posés au niveau de la session (même correctif que le 🟡 du gourou dev) | APPROUVÉ |
| 13 | 14 | ff85f6b5 | dev | Tour 12 en partie validé. 🟡 maintenu, avec un nouveau mécanisme : les options du DSN sont ignorées par `constructPdoDsn()` (DBAL 4.5) et par `PdoSessionHandler::buildDsnFromUrl()`, et le code l'a confirmé. ⚪ : lieu de la traduction de 55P03 / 57014 / `LockAcquiringException`, réponse en cas de contention de session | Intégré en rév. 15 : middleware de pilote DBAL `SessionTimeoutsDriverMiddleware`, limité à `rate_limiter` (deux `SET` après `connect`) ; DSN PDO natif `pgsql:…;options='-c …'` pour les sessions, sans `PGOPTIONS` ni `ALTER ROLE` ; tests `SHOW` sur chaque connexion. ⚪ intégrés : traduction dans `SymfonyRateLimiterThrottle` et `LoginRateLimiter` (DBAL + `LockAcquiringException`) ; 503 sans création de session | OBJECTIONS |
| 13 | 14 | ff85f6b5 | ddd | Tour 12 validé. 🟡 : même constat que le gourou dev sur les options du DSN. ⚪ : la liste des commandes qui verrouillent `User` est incomplète (`DisableTotp`, `RegenerateBackupCodes`, `StartTotpEnrollment`) ; « Co-Authored-By » signalé | Intégré : même correctif. ⚪ intégré : « toute commande qui modifie `SecondFactor`, `BackupCode`, `EmailLoginCode` ou `Credentials` verrouille `User` », avec la liste complète. « Co-Authored-By » : la règle de commit de l'utilisateur (`~/.claude` rules/git-commit.md) prime explicitement sur l'attribution par défaut, c'est une donnée attendue | OBJECTIONS |
| 13 | 14 | ff85f6b5 | security | Tour 12 validé. Décision 24 : désaccord maintenu en ⚪. 🟡 : même constat sur les options du DSN, vérifié dans `vendor/`. ⚪ : traduction de `LockAcquiringException`, contention de session en 503 sans repli anonyme | Intégré : même correctif, avec un test de 503 en moins de 3 s pour un verrou de session. ⚪ intégrés : traduction nommée et une seule entrée d'audit ; 503 sans création ni régénération de session | OBJECTIONS |
| 14 | 15 | 43008b5d | dev | Tour 13 validé, mécanisme vérifié dans `vendor/` (`MiddlewaresPass`, `PdoSessionHandler` L169). ⚪ seulement : traduction des exceptions écrite deux fois ; identifiants de la fabrique de DSN et calcul dans le constructeur ; `statement_timeout` de 5 s face à `prune` | Notes d'implémentation 9 à 11, ci-dessous | APPROUVÉ |
| 14 | 15 | 43008b5d | ddd | Tour 13 validé, mécanisme vérifié dans `vendor/`. ⚪ seulement : la fabrique de DSN doit transmettre les identifiants et `sslmode` ; connexion utilisée par `prune` ; lien Chrome | Notes d'implémentation 10 et 11 ; lien Chrome : donnée attendue | APPROUVÉ |
| 14 | 15 | 43008b5d | security | Tour 13 validé, mécanisme vérifié dans `vendor/`. Décision 24 : désaccord maintenu en ⚪. ⚪ seulement : mot de passe exclu du DSN des sessions ; validation de la syntaxe conninfo | Notes d'implémentation 10 et 12 | APPROUVÉ |

### Notes d'implémentation, suite (⚪ du tour 14, hors contenu approuvé)

9. **Un seul traducteur d'exceptions.** `RateLimiterStorageFailure::translate(Throwable)` est un service d'Infrastructure, composé par `SymfonyRateLimiterThrottle` et `LoginRateLimiter`. Il traduit 55P03, 57014 et `LockAcquiringException` en `RateLimiterStorageUnavailable`, et il a son test unitaire.
10. **Fabrique du DSN des sessions.**
    - L'utilisateur et le mot de passe, décodés par `rawurldecode`, passent par les options `db_username` / `db_password` de `PdoSessionHandler`, **jamais dans le DSN**.
    - `sslmode` et les autres paramètres libpq de l'URL sont reportés dans le DSN.
    - Le calcul se fait dans une méthode : le constructeur ne contient que des assignations.
    - Un test unitaire couvre un mot de passe avec des caractères encodés, la conservation de `sslmode`, l'absence de `password=` dans le DSN, et l'échappement des quotes de `options`.
11. **`app:rate-limiter:prune`** passe par la connexion principale, et non par `rate_limiter`, ou supprime par lots bornés. Il n'est donc pas coupé par le `statement_timeout` de 5 s.
12. **Syntaxe conninfo.** La fabrique décode l'URL une seule fois, vérifie que le port est numérique et refuse `;` et `'` dans l'hôte et le nom de base. Un test le vérifie.

**Unanimité au tour 14, révision 15, hash `43008b5d`.** Depuis le tour 6, chaque gourou a apporté :
- **dev** : l'Application isolée de Lock et de RateLimiter par des ports, la Strategy `CodeCheck`, des délais réellement appliqués (middleware de transaction, middleware de pilote, DSN natif) ;
- **ddd** : l'émetteur de `SecondFactorThrottled`, une seule forme de `Throttled` par type de commande, des invariants protégés par des verrous bornés ;
- **security** : `peek` qui refuse vraiment, un stockage des limiteurs en échec fermé et sans nouvel essai, `reset()` du login sans remise à zéro par IP, des délais vérifiés dans les sources.

Les retours de l'utilisateur à la révision 6 (Mailpit, rate-limiter, sessions en base) et la décision 30 (mode worker en production) sont intégrés.

**Présentation de la révision 15 refusée par l'utilisateur.** Retour : « Utilise Turbo avec les Turbo Frames et les placeholders pour charger les données. » Deux questions lui ont été posées. Réponses : frames lazy pour les zones lourdes seulement ; frame ciblée et Turbo Stream après une action. C'est consigné en décision 31 (révision 16), avec la section « UI : Turbo Frames, placeholders et Turbo Streams », l'étape 13 et `design.md` §5. Le contenu approuvé a changé : un tour complet suit.
| 15 | 16 | 61946a39 | dev | Tour 14 validé. 🟡 : contenu d'une frame assemblé à deux endroits (endpoint et stream) ; réponse d'action rédigée dans chaque contrôleur ; URL de frame qui devient une URL de page (pagination avec `advance`, chemin de retour après le login) ; les « trois cas » de `frame_state_controller` ne correspondent pas aux événements de Turbo 8.0.23 (5xx et redirection passent tous deux par `frame-missing`, une erreur réseau par `fetch-request-error`). ⚪ : fermeture du dialog, cache de pages, nonce CSP, CSRF par en-tête, tests navigateur | Intégré en rév. 17 : `FrameView` unique par case de `TurboFrame` (`id`, `route`, `parentRoute`), composé par l'endpoint et par le stream, avec un data provider sur l'enum ; `Shared\UI\ActionResponder` (choix stream ou 303, une seule table de correspondance des refus, table action → frames) ; pagination vers l'URL de la page, 303 sans `Turbo-Frame`, chemin de retour sans routes de frame, et tests ; un seul handler `frame-missing` qui tranche sur la réponse, `fetch-request-error` pour le réseau, 403 et 404 rendus dans `<turbo-frame>`, `<template>` d'erreur rendu par le serveur. ⚪ intégrés : `turbo:submit-end->dialog#closeOnSuccess`, balise `turbo-cache-control`, nonce `CspNonce` (`ResetInterface`), jetons CSRF stateful documentés, test navigateur en non-objectif avec vérification manuelle | OBJECTIONS |
| 15 | 16 | 61946a39 | ddd | Tour 14 validé. 🟡 : refus venus du `query.bus` jamais audités (pas de middleware sur ce bus, et le listener ignore ces exceptions). ⚪ : `QuotaExceeded` sans nom, identifiants de frame entre contextes, table action → frames | Intégré : `AuditDeniedQueryMiddleware` et marqueur « déjà audité », le listener n'audite que les refus non marqués, test « une seule entrée `denied` ». ⚪ intégrés : exception `QuotaExceeded(quotaName, limit)` (`denied` / `quota`, 422) ; la page hôte ne référence que le nom de route, l'id est rendu par l'endpoint ; table action → frames par contexte | OBJECTIONS |
| 15 | 16 | 61946a39 | security | Tour 14 validé. Décision 24 : désaccord maintenu en ⚪. 🟡 : le cache de pages de Turbo réaffiche, après l'expiration de la session, les pages visitées et les codes de secours (vérifié dans Turbo 8.0.23 : `shouldIssueRequest`, `cacheSnapshot`). ⚪ : `Turbo.visit` vers une autre origine, chemin de retour sur une frame, bruit dans l'audit (frames non autorisées, prefetch), CSP et barre de progression, `Vary: Accept` | Intégré : `<meta name="turbo-cache-control" content="no-cache">` dans le layout authentifié, `Turbo.cache.clear()` sur `frame-missing`, logout en POST qui purge le cache, avec un test. ⚪ intégrés : contrôle de même origine ; chemin de retour sans routes de frame ; frames incluses seulement sous `is_granted`, `turbo-prefetch` à false ; nonce par requête sans `unsafe-inline` ; `Vary: Accept, Turbo-Frame` | OBJECTIONS |
| 16 | 17 | 9ba4a364 | dev | Tour 15 validé. 🟡 : `parentRoute()` oblige une frame d'Audit à nommer une route d'Organization (en dur ou par import, et sans ses paramètres). ⚪ : `render(): string` perd le statut et l'autorisation est jugée deux fois ; `ActionResponder` type des enums de contexte, et on ne sait pas qui lit la table ; table des refus sans 503 ni cas par défaut ; marqueur « déjà audité » mutable | Intégré en rév. 18 : `fallbackRoute(FrameContext): RouteReference` vers une page du **même** contexte (`/teams/{teamId}/audit` pour Audit), vérifiée par le data provider. ⚪ intégrés : le handler de requête est le seul juge, `FrameView` n'appelle plus de voter, `FrameExceptionRenderer` unique ; interface `Shared\UI\Frame`, le responder lit la table, une table par contexte ; table des refus complète (409, 503, 500, 422 avant `dispatch`) ; enveloppe immuable `AlreadyAudited(Throwable)` | OBJECTIONS |
| 16 | 17 | 9ba4a364 | ddd | Tour 15 validé. 🟡 : frames relues après une action sans vérifier leur visibilité (fausse entrée `denied` après une auto-rétrogradation) ; refus du voter dans `FrameView` audité deux fois ou pas du tout ; table des refus sans les refus métier. ⚪ : « méthodes métier » au lieu de « méthodes de présentation », noms de route entre contextes | Intégré : contrôle de visibilité par `is_granted` (non audité) avant de recomposer, `remove` pour une frame devenue invisible, 303 si plus rien n'est visible, avec un test ; un seul juge, le handler de requête ; famille `BusinessRuleViolated(ruleKey)` (`QuotaExceeded`, `LastTeamAdminRequired`, `ProjectNotEmpty`…) en 422, plus 503 et 409. ⚪ intégrés : « méthodes de présentation » ; test d'existence des noms de route référencés par une page hôte | OBJECTIONS |
| 16 | 17 | 9ba4a364 | security | Tour 15 validé. Décision 24 : désaccord maintenu en ⚪. 🟡 : sous Turbo Drive, un POST doit rediriger (vérifié dans Turbo 8.0.23, `requestMustRedirect`), ce qui pousse à passer les codes de secours par la session. ⚪ : la CSP bloque les attributs `style` du kit (`MenuSkeleton`, `Tooltip`), frame relue après une perte de droit, curseur et portée de l'audit, rendu et audit de la 403 / 404 dans la frame | Intégré : codes générés côté UI (`BackupCodeGenerator`), seuls les hashes sont stockés ; formulaires en `data-turbo="false"` rendus en 200 avec `no-store`, exclus du repli 303 ; ni flash ni session ; test « aucun code dans `sessions` ni dans l'audit ». ⚪ intégrés : attributs `style` remplacés par des classes ou du CSSOM, `<meter>` pour les jauges, test d'absence de `style=` ; même contrôle de visibilité que pour le gourou ddd ; VO `AuditCursor`, filtres en liste blanche, `team_id` lu dans la route, frame d'audit dans le test à deux équipes ; `FrameExceptionRenderer` et `AlreadyAudited` | OBJECTIONS |
| 17 | 18 | f5f50517 | dev | Tour 16 validé. 🟡 : `ActionResponder` ne distingue pas l'issue de la commande du rendu des frames. Une frame qui échoue après un `dispatch` réussi présentait l'action commitée comme une 500, et l'utilisateur, en recommençant, recevait une 409. ⚪ : deux formes d'entrée sur une même méthode ; liste d'exceptions pour les actions qui affichent un secret ; agrégation des tables action → frames non nommée ; correspondance case → `FrameView` non vérifiée | Intégré en rév. 19 : « ce qui est commité ne se dément pas ». L'issue de la commande fixe le statut et l'alerte, chaque frame est recomposée isolément, une frame en échec passe en état d'erreur avec « Retry » sous une réponse 200, sans entrée d'audit supplémentaire. Une ligne est ajoutée à la table, avec un test. ⚪ intégrés : méthodes `invalid()` et `dispatched()` ; Strategy `SecretRevealingResponse` choisie par les deux contrôleurs ; port tagué `ActionFrameMap` ; assertion « un `FrameView` par case » | OBJECTIONS |
| 17 | 18 | f5f50517 | ddd | Tour 16 validé. ⚪ : audit de `InvalidSecondFactorTransition` contradictoire entre deux passages ; emplacement de `BusinessRuleViolated` ; `ConfirmTotp` ne reçoit pas les codes ; `Throttled` face à l'anti-énumération ; frames d'un autre contexte non rafraîchies ; ligne vide | ⚪ intégrés : une seule vérité (`denied` / `rule:…`) ; `Shared\Domain\BusinessRuleViolated` ; `ConfirmTotp` reçoit les codes ; les pages d'authentification ne passent pas par `ActionResponder` ; rafraîchissement entre contextes via `ActionFrameMap`, sinon au prochain chargement (assumé) ; ligne vide supprimée | APPROUVÉ |
| 17 | 18 | f5f50517 | security | Tour 16 validé ; vérifié Messenger (`HandleMessageMiddleware`) et `zend.exception_ignore_args` en production. Décision 24 : désaccord maintenu en ⚪. ⚪ : secrets en clair dans les commandes, protégés seulement par un réglage d'environnement ; `--skeleton-width` ne peut pas devenir une classe | ⚪ intégrés : `#[\SensitiveParameter]` sur les paramètres qui portent un secret, avec un test d'architecture ; trois attributs `style` précisément listés, paliers de largeur ou CSSOM pour `--skeleton-width` | APPROUVÉ |
| 18 | 19 | 3816c13d | dev | Tour 17 validé. 🟡 : le chemin d'échec d'une action n'a pas de propriétaire. `dispatched()` ne voit que les succès et `FrameExceptionRenderer` ne voit que les frames. En plus, `AlreadyAudited` ne traverse pas le bus comme prévu : `UnwrapsHandlerFailure` ne déroule que `HandlerFailedException`, et lui apprendre à retirer l'enveloppe ferait réauditer. ⚪ : contradiction sur le `denied` de la relecture ; SRP d'`ActionResponder` ; `object $command` mal typé | Intégré en rév. 20 : ce qui sort des bus est toujours `AlreadyAudited`, avec `cause()`. Les middlewares déroulent eux-mêmes `HandlerFailedException` ; aucun bus ne retire l'enveloppe. Un test vérifie ce format pour chaque bus. `ActionResponder::handle(Form, Closure → AuditableCommand, RouteReference)` en *execute around* couvre la validation, le succès et le refus, et re-rend le formulaire avec ses saisies, testé. ⚪ intégrés : le `denied` de la relecture reste écrit (avec un test) ; façade composée de `FrameRefresher` et de `ResponseFormat` ; `AuditableCommand` vérifiée par PHPStan | OBJECTIONS |
| 18 | 19 | 3816c13d | ddd | Tour 17 validé. 🟡 : le refus d'une commande n'a pas de point d'entrée dans `ActionResponder`. ⚪ : `denied` de la relecture, typage `AuditableCommand` | Intégré : même correctif `handle()` en *execute around*, avec le test « `QuotaExceeded` → 422 dans la frame du formulaire, une seule entrée `denied` ». ⚪ intégrés : formulation sur le `denied` de la relecture alignée dans le texte et dans la table ; `AuditableCommand` | OBJECTIONS |
| 18 | 19 | 3816c13d | security | Tour 17 validé. Décision 24 : désaccord maintenu en ⚪. ⚪ : divergence voter/handler à auditer en `denied` ; contenu du journal pour un échec de frame ; garde-fou contre l'oubli de `SecretRevealingResponse` | ⚪ intégrés : `denied` conservé, avec un test `success` + `denied` ; journal limité à la classe de l'exception, à l'id de la frame et au request id ; interface marqueur `RevealsSecret` et `LogicException` dans `handle()`, testées | APPROUVÉ |
| 19 | 20 | 2a16818e | dev | Tour 18 validé en partie (format de sortie des bus accepté). 🟡 maintenu, avec une portée réduite : `handle(FormInterface…)` ne couvre ni les boutons seuls (`isCsrfTokenValid()`, sans formulaire), ni le re-rendu du formulaire (template et frame inconnus), ni les actions qui affichent un secret, qui contournent `handle()`. ⚪ : note d'implémentation 1 périmée, table Markdown de `SecondFactor` cassée, étapes 3 et 13 incomplètes | Intégré en rév. 21 : les boutons deviennent des formulaires sans champ (`ActionButtonType`, un `csrf_token_id` par action), donc tout changement d'état passe par Form et par `handle()`. `handle(ActionForm, Closure, ResponseFormat, RouteReference)` reçoit le formulaire, sa frame et son template, ainsi que la Strategy. Les actions qui affichent un secret passent par `handle()` avec `SecretRevealingResponse`, et un garde-fou `RevealsSecret` s'applique dans les deux sens. ⚪ intégrés : note 1 corrigée ci-dessous, liste sortie de la table, étapes 3, 9 et 13 complétées | OBJECTIONS |
| 19 | 20 | 2a16818e | ddd | Tour 18 validé. ⚪ : `AlreadyAudited` sans l'action (pour `event.handler.failed`) ; tableau L253 en retard ; espace de nommage d'`AlreadyAudited` ; pages d'authentification qui doivent lire `cause()` | ⚪ intégrés : `action(): AuditAction` posée par le middleware d'audit et lue par `PublishDomainEventsMiddleware` ; ligne 2 du tableau alignée ; `Shared\Application\Audit\AlreadyAudited` ; les pages d'authentification lisent `cause()` sans réauditer | APPROUVÉ |
| 19 | 20 | 2a16818e | security | Tour 18 validé, et `UnwrapsHandlerFailure` vérifié dans le code. Décision 24 : désaccord maintenu en ⚪. ⚪ : un jeton CSRF absent donne 422 au lieu de 403 et n'est pas audité ; note 1 périmée | ⚪ intégrés : `handle()` distingue l'erreur CSRF (403, une seule entrée `denied` / `csrf`), et le test est aligné ; note 1 corrigée | APPROUVÉ |

**Correction de la note d'implémentation 1** (les notes, sous le marqueur, sont en ajout seul ; cette ligne remplace la note 1) : `ResetUnitOfWorkOnFailureMiddleware` (ou `ResolveAuditScopeOnFailureMiddleware`) pose `AuditScopeStamp` sur l'enveloppe de la `HandlerFailedException` reconstruite. `AuditFailureMiddleware` lit ce stamp **avant** de dérouler `HandlerFailedException`, puis relance l'exception métier enveloppée dans `AlreadyAudited` (avec `cause()` et `action()`). L'UI lit **`AlreadyAudited::cause()`**, et non `UnwrapsHandlerFailure`, qui ne retire jamais l'enveloppe.
| 20 | 21 | 8648fa36 | dev | Tour 19 validé. ⚪ : répartition entre les commits 2 et 3 (le commit 2 ne compilerait pas sans le socle UI de Shared) ; détection du CSRF par `getCause()` ; SRP du responder qui écrit l'audit CSRF ; pages d'authentification hors de la table des refus | ⚪ intégrés en rév. 22 : tout le socle UI de Shared passe à l'étape 9 (commit 2), et l'étape 13 ne garde que la partie Organization et Audit ; détection par `getErrors(true)` avec `getCause()` de type `CsrfToken` ; collaborateur `CsrfRejection` testé seul ; les pages d'authentification réutilisent la table des refus | APPROUVÉ |
| 20 | 21 | 8648fa36 | ddd | Tour 19 validé. 🟡 : L235 et L836 se contredisent sur l'acceptation d'invitation, et le CSRF des pages d'authentification n'a pas de propriétaire. ⚪ : `AuditAction` du refus CSRF ; `ConfirmTotp` avec un code faux | Intégré : liste exacte et fermée des sept routes d'authentification (l'acceptation d'invitation en fait partie et sort de la liste des boutons), CSRF explicite pour chacune, `CsrfRejection` partagé, test étendu aux sept routes. ⚪ intégrés : action `csrf.rejected` avec `Scope::none()` ; `ConfirmTotp` passe par `SecondFactorAttempt` (`Rejected` donne 422 et une seule entrée `failure`) | OBJECTIONS |
| 20 | 21 | 8648fa36 | security | Tour 19 validé. Décision 24 : désaccord maintenu en ⚪. 🟡 : le CSRF des pages d'authentification n'est décrit nulle part (« voir plus bas » sans contenu), régression de l'objection du tour 5. ⚪ : ordre du garde-fou `RevealsSecret` par rapport au `dispatch`, action et portée de l'entrée CSRF, re-rendu avec les saisies | Intégré : même correctif, avec scheb en `enable_csrf: true` et Form avec CSRF sur les autres pages, et sept routes dans le test 403. ⚪ intégrés : contrôle de cohérence **avant** le `dispatch`, avec un test « aucune entrée `success` » ; `csrf.rejected` dont le contexte ne contient que `csrf_token_id` ; `PasswordType` avec `always_empty`, codes jamais présents dans un formulaire, test sur la 422 | OBJECTIONS |

| Tour | Rév. | Hash | Gourou | Points majeurs | Traitement | Verdict |
|---|---|---|---|---|---|---|
| 21 | 22 | 4114e870 | dev | Tour 20 validé. 🟡 : sur `/login` et le second facteur, un jeton CSRF invalide lève `InvalidCsrfTokenException` (une `AuthenticationException`), d'où une 302 et un `LoginFailureEvent`, jamais `CsrfRejection` ni la 403 annoncée. Vérifié dans `vendor/` (`AuthenticatorManager`). Le logout n'a pas de propriétaire. ⚪ : libellé `denied` / `csrf` contre `csrf.rejected` ; tableau du journal coupé | Intégré en rév. 23 : option (a). `CsrfAwareFailureHandler` en `failure_handler` sur `form_login` et `two_factor`, qui délègue à `CsrfRejection` (403, `csrf.rejected`) ; le subscriber d'audit d'authentification ignore ce cas ; le logout (8ᵉ route) passe par `CsrfRejection` via le listener ; test sur huit routes, sans doublon. ⚪ intégrés : libellé unifié `csrf.rejected` ; en-tête du tableau du journal répété | OBJECTIONS |
| 21 | 22 | 4114e870 | ddd | Tour 20 validé. 🟡 : `ConfirmTotp` avec un code faux. Le `dispatch` réussit, donc `SecretRevealingResponse` affiche des codes non stockés ; `AuditSuccessMiddleware` écrit un `success` en plus du `failure` ; `TotpCheck` appelle `verifyTotp`, invalide sur `PendingTotp` ; `confirmTotp` n'a pas d'`attemptId`. ⚪ : CSRF du logout | Intégré : `User::confirmTotp(step, attemptId, backupCodeHashes, now)` renvoie un résultat ; Strategy `TotpEnrollmentCheck` ; `ConfirmTotp` devient une `SelfAuditedCommand` ; `SecretRevealingResponse` lit `GetCodeVerificationOutcome` et n'affiche les codes que sur `Accepted` ; test « 422, une seule entrée `failure`, aucun code, toujours `PendingTotp` ». ⚪ intégré : logout via `CsrfRejection` | OBJECTIONS |
| 21 | 22 | 4114e870 | security | Tour 20 validé. Décision 24 : désaccord maintenu en ⚪. 🟡 : même constat que le gourou dev sur le CSRF de `form_login` et de scheb (redirection 302, audit sous une autre action), vérifié dans `vendor/`. ⚪ : logout audité comme un `denied` générique | Intégré : même correctif (a), avec un test d'une seule entrée sur les deux routes. ⚪ intégré : logout via `CsrfRejection` | OBJECTIONS |
| 22 | 23 | 71a7b872 | dev | Tour 21 validé. Vérifié dans les sources de scheb et Symfony : `failure_handler` accepté, badge CSRF à la priorité 512 avant le code à 0, `onAuthenticationFailure` appelé avant `LoginFailureEvent`. ⚪ seulement : priorité du listener du logout face à `Firewall\ExceptionListener` (priorité 1) ; l'événement `FAILURE` de scheb ne doit pas être audité ; décomptes « trois » au lieu de quatre ; un rejet CSRF au login consomme `login_throttling` | Notes d'implémentation 13 à 16, ci-dessous | APPROUVÉ |
| 22 | 23 | 71a7b872 | ddd | Tour 21 validé : `ConfirmTotp` et logout traités. ⚪ seulement : décomptes « trois » ; `ConfirmTotp` absent des listes de limiteurs ; `TotpEnabled` seulement sur `Accepted` ; `revokeAll()` révoque aussi la session courante | Notes d'implémentation 15, 17 et 18 | APPROUVÉ |
| 22 | 23 | 71a7b872 | security | Tour 21 validé. Décision 24 : désaccord maintenu en ⚪. ⚪ seulement : `LogoutException` enveloppée par le firewall ; `failure_handler` qui supprime le handler par défaut (à composer) ; quota de connexion entamé avant le CSRF | Notes d'implémentation 13, 14 et 16 | APPROUVÉ |

### Notes d'implémentation, suite (⚪ du tour 22, hors contenu approuvé)

13. **Logout.** Le listener qui délègue à `CsrfRejection` écoute `kernel.exception` avec une **priorité supérieure à 1**, donc avant `Firewall\ExceptionListener`. Sinon, il reconnaît une `AccessDeniedHttpException` dont `getPrevious()` est une `LogoutException`. Le test « logout sans jeton → 403, une seule entrée `csrf.rejected` » est bloquant.
14. **`CsrfAwareFailureHandler`.** Il **compose explicitement** les handlers par défaut que Symfony et scheb ne construisent plus dès qu'un `failure_handler` est configuré : `DefaultAuthenticationFailureHandler`, avec les options de `form_login`, et le handler d'échec par défaut de scheb.
    - Test : un mauvais mot de passe donne toujours une 302 vers `/login` avec l'erreur générique.
    - Test : un mauvais code de second facteur revient toujours sur le formulaire de 2FA.
15. **Audit et décomptes.**
    - Le subscriber d'audit d'authentification n'écoute que `LoginFailureEvent`, **jamais `TwoFactorAuthenticationEvents::FAILURE`** de scheb, qui ne porte pas l'exception.
    - Corriger « ces trois commandes auto-auditées » en **quatre**, et « les trois facteurs » en **trois facteurs, quatre gestes**.
    - Ajouter `ConfirmTotp` (enrôlement) aux listes des limiteurs du second facteur et des handlers qui passent par `AttemptThrottle`.
16. **Rejet CSRF à la connexion.** Il compte dans `login_throttling`, car le limiteur est consommé avant ou pendant l'échec. C'est conservateur, voulu et documenté. Le test des huit routes en tient compte.
17. **`TotpEnabled`.** `confirmTotp` ne l'enregistre **que sur `Accepted`**. L'email d'alerte de la décision 26 en dépend. Un cas est ajouté au test de la matrice `SecondFactor`.
18. **`revokeAll()` après `ConfirmTotp` ou `RegenerateBackupCodes`** révoque **aussi la session courante**. Les codes s'affichent bien dans la réponse en 200, puis l'utilisateur se reconnecte avec son nouveau facteur, ce qui prouve que l'enrôlement fonctionne. Ce choix est consigné dans les cas limites et dans la vérification manuelle (étape 2).

**Unanimité au tour 22, révision 23, hash `71a7b872`.** Depuis la décision 31 (Turbo), chaque gourou a apporté :
- **dev** : un `FrameView` unique par frame, `ActionResponder` en *execute around* (`ActionForm`, `ActionButtonType`, Strategies `ResponseFormat`), `AlreadyAudited` qui traverse les bus avec `cause()` et `action()`, et la règle « ce qui est commité ne se dément pas » ;
- **ddd** : l'audit des refus sur le `query.bus`, la famille `BusinessRuleViolated`, la visibilité vérifiée avant le rafraîchissement, `fallbackRoute` limité à son contexte, et `ConfirmTotp` cohérent (`TotpEnrollmentCheck`) ;
- **security** : le cache de pages de Turbo désactivé, l'affichage des codes de secours sans passer par la session, la CSP sans `style` inline, un CSRF uniforme sur les huit routes d'authentification (`CsrfAwareFailureHandler`), et `#[\SensitiveParameter]`.

Les retours de l'utilisateur (décisions 27 à 31) sont tous intégrés.
