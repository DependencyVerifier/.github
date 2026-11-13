# DependencyVerifier — Surveillance des dépendances et CVE par agent

> Nom du projet : **DependencyVerifier** (anciennement « DepRadar », abandonné car déjà pris). Identifiant technique court `depverify` : console `depverify`, agent `depverify-agent`, image `ghcr.io/dependencyverifier/agent`, organisation GitHub `DependencyVerifier` (dépôts `console`, `agent`, `agent-image`), préfixe des labels Docker `dev.depverify.*`, console locale `https://console.depverify.localhost`.
> Document de cadrage destiné à servir de contexte de travail (humain ou IA) pour la conception et le développement.
> Auteur : Romain Millan — dernière mise à jour : 09/11/2026 (ajouts : authentification par passkey, design de la console, architecture DDD, healthcheck, domaine configurable, 2FA des admins).

---

## 1. Problème

Je gère de nombreux projets web et non-web, hébergés soit sur mes serveurs, soit chez des tiers. À chaque déploiement, des CVE sont découvertes sur les dépendances ou les runtimes, trop tard. Il n'existe aucune vue consolidée de **ce qui tourne réellement en production** (versions de PHP/Node, dépendances Composer/npm, paquets système, images Docker) ni d'alerte proactive quand une nouvelle CVE touche un de ces éléments.

## 2. Vision

Une application **open source, auto-hébergée**, composée de :

- une **console** web multi-équipes qui centralise l'inventaire de tous les projets, le croise en continu avec les bases de vulnérabilités et de fin de vie, et notifie selon les préférences de chaque projet ;
- un **agent** léger installé sur chaque serveur (`curl … | sh`), qui inventorie ce qui est déployé et le remonte à la console par une connexion **sortante uniquement**, chiffrée et signée.

### Différenciateur

Les outils existants (Dependabot, Renovate, Snyk, Trivy, OWASP Dependency-Track) partent surtout du **repo** ou de la **CI**. Ici, la source de vérité **du MVP** est **la machine en production**, ce qui couvre aussi :

- les serveurs hébergés par des tiers, sans accès au dépôt Git ;
- l'écart entre ce qui est dans le repo et ce qui est réellement déployé ;
- les runtimes et paquets système, que les outils centrés sur le repo ignorent ;
- une organisation multi-équipes et multi-environnements, adaptée à quelqu'un qui gère des projets pour plusieurs personnes.

> **À garder en tête dès la conception :** l'agent n'est que la **première source d'inventaire**. D'autres viendront : dépôt Git (API GitHub/GitLab), pipeline CI (envoi de SBOM), upload manuel de fichiers (lockfile, SBOM)… Le moteur d'analyse, le modèle de données et les notifications ne doivent **jamais dépendre de l'agent**. Ils consomment un inventaire normalisé (SBOM CycloneDX + faits de l'environnement d'exécution), quelle que soit sa provenance (voir §5, `InventorySource`).

### Principes de sécurité de l'agent

- agent en connexion sortante seule ;
- appairage avec validation humaine ;
- ordres signés Ed25519 avec anti-rejeu ;
- épinglage de la clé de la console ;
- secrets jamais relisibles ;
- journal d'audit inaltérable.

## 3. Décisions prises

| Sujet | Décision |
|---|---|
| Modèle de distribution | **Open source, self-hosted.** Chaque utilisateur héberge sa console. Instance de référence : un serveur de Romain, avec au moins 2 équipes (projets perso, projets hébergés gratuitement pour des tiers). |
| Licence | **Console en AGPL-3.0, agent en Apache-2.0.** |
| Stack console | **Symfony + PostgreSQL** (voir §9). |
| Langage agent | **Rust** (voir §6). |
| Hôtes et équipes | **Un hôte appartient à une seule équipe.** Les équipes sont isolées au niveau de l'infra (LXC ou VM distincts), donc un agent ne sert jamais deux équipes. |
| Agent, hôte et projets | **1 agent = 1 périmètre de collecte** : un hôte (mode `host`), un projet Compose ou un hôte Docker (mode `container`, sans rien installer sur l'hôte), un conteneur (mode `embedded`, secours), ou un compte+région AWS (mode `ecs`). Un hôte peut porter plusieurs projets de la même équipe, et un projet peut tourner sur plusieurs hôtes (voir §5bis). |
| Conteneurs / ECS | Pour les applications 100 % Docker, l'unité d'inventaire est l'**image (par digest)**. 4 déploiements possibles, avec le même binaire : `host` (sur le serveur), `container` (image officielle, un service dans le `docker-compose.yml`, portée réglable par `AGENT_SCOPE` et par labels Docker), `embedded` (dans l'image de l'application, secours), `ecs` (collecteur via l'API AWS pour Fargate, **hors MVP**). Voir §6bis. |
| Identifiants | **UUID (v7) pour toutes les entités** : équipe, projet, environnement, hôte, agent, application, etc. Aucun identifiant auto-incrémenté ni nom utilisé comme référence technique (voir §5). |
| Création des équipes | Par le **super admin**, avec des **quotas** par équipe (projets, agents, membres…). Des **quotas par défaut** définis dans la configuration de l'instance s'appliquent à la création. |
| Dépassement de quota | **Blocage strict, super admin compris** : il doit d'abord relever le quota de l'équipe (décision du 09/11/2026). |
| Super admin | **Pleins pouvoirs sur toute l'instance**, y compris l'appairage des agents. Seul un autre super admin peut lui retirer `ROLE_SUPER_ADMIN`. |
| Validation des agents | Par les **admins de l'équipe**, sans avoir besoin du super admin (qui peut aussi le faire). |
| Droits | **Rôles fixes + permissions additionnelles accordées individuellement**, à 3 niveaux : instance (super admin), équipe, projet. Un utilisateur peut appartenir à plusieurs équipes sans les gérer, et ne voir que certains projets de chacune (voir §7bis). |
| Destinataires de notifications | **Toujours un compte `User`.** Un destinataire sans accès à la console est un compte **« notification seule »**, qui ne peut pas se connecter. |
| Sources d'inventaire (MVP) | **Agent uniquement.** L'architecture **doit** permettre d'ajouter plus tard d'autres sources : API Git, envoi depuis la CI, upload manuel. |
| Écosystèmes MVP | PHP/Composer, Node (npm/yarn/pnpm), paquets OS (dpkg/rpm/apk), conteneurs Docker. |
| Hôtes supportés | Linux (VM / bare metal, systemd), Docker / Compose, ECS sur EC2 (agent en service « daemon »). **ECS Fargate hors MVP** (mode `ecs`, roadmap). Pas de Kubernetes, de mutualisé ni de Windows au MVP. |
| Découverte des applications | **Les deux modes** : découverte automatique dans des racines configurables avec validation par l'admin, et chemins déclarés manuellement. |
| Modèle d'organisation | **Équipe > Projet > Environnement > Hôte.** |
| Périmètre de l'analyse | CVE, fin de vie des runtimes, fin de vie des frameworks, dépendances obsolètes. |
| Actions | **Notification uniquement** : email et webhook custom, Slack/Teams/etc. en bonus. Pas de création de ticket ni de PR au MVP. |
| Gestion du bruit | Seuil de sévérité, digest périodique, acceptation de risque, alerte « agent muet ». **Tout est configurable par projet.** |
| Authentification | Comptes locaux. **Connexion principale : email + mot de passe, puis un second facteur** : TOTP si l'utilisateur l'a configuré, sinon code à usage unique envoyé par email. **Passkey (WebAuthn) proposée en option, jamais obligatoire** : clé matérielle type YubiKey, trousseau iCloud, gestionnaire de mots de passe type Bitwarden. Pas de connexion via GitHub ni d'inscription libre. **Pas d'API publique ni de jetons d'API au MVP** : l'API complète (lecture + écriture) arrivera avec les sources CI et Git. Pas de SSO au MVP, mais il reste prévu dans le design (voir §7). |
| Domaine | **Aucun domaine imposé.** Chaque instance est auto-hébergée et configure son URL publique (`SERVER_NAME`, `DEFAULT_URI` ; le `rpId` des passkeys en découle). Instance de référence : `console.depverify.romainmillan.fr`. Les identifiants techniques sont des constantes du produit, indépendantes du domaine : binaire `depverify-agent`, labels `dev.depverify.*`, image `ghcr.io/dependencyverifier/agent`, organisation GitHub `DependencyVerifier`. En local : `https://console.depverify.localhost`. |
| Design de la console | Interface **sobre et dense, inspirée de shadcn/ui** : sidebar à gauche, en-têtes d'objet, cartes de métadonnées, onglets, thème clair / sombre / système. **Symfony UX Toolkit (kit `shadcn`) + Tailwind CSS v4**, compilé par Vite via Symfony Reprise. Polices auto-hébergées (voir §9 et `docs/design.md`). |
| Autoscaling | **Jeton d'enrôlement réutilisable**, validé une fois par un humain, limité en nombre d'agents et dans le temps. Les agents enrôlés avec ce jeton sont validés automatiquement (voir §6). |
| Mode `embedded` | Agent dans l'image de l'application, en secours (décision 25, §6bis.3). |
| Registres d'images applicatives | **Aucun accès registre au MVP, quelle que soit l'origine de l'image** : GitHub Container Registry, registre privé ou **image construite sur le serveur** avec un Dockerfile. Dès qu'un conteneur tourne, son image est présente dans le moteur Docker local, et l'agent la lit via l'API Docker. Il n'a besoin d'aucun identifiant de registre. L'accès aux registres n'arrivera qu'avec le collecteur Fargate (voir §6bis, « Identité d'une image »). |
| Distribution de l'agent | **GitHub public** : binaires (GitHub Releases, signés minisign) et image Docker (`ghcr.io`, signée cosign), utilisables par tous. La console vérifie les signatures avant de servir une version. **Import manuel** d'un binaire signé possible pour les instances sans accès Internet. |
| Dimensionnement | **Cible MVP ≤ 200 agents** par instance. Le design doit permettre de monter à **≤ 2 000 agents** sans refonte (voir §9bis). |
| Carte des contextes (console) | **Identity et Organization ne s'importent jamais.** Identity consomme le contrat `FindPendingInvitation` / `AcceptInvitation` d'Organization ; Organization consomme `FindAccounts`, `SearchAccounts`, le port `AccountProvisioning` (appelé dans la transaction de `CreateTeam`, jamais par un dispatch imbriqué sur le bus de commandes) et les événements d'intégration `AccountDeactivated` / `AccountReactivated` d'Identity. Relation client / fournisseur dans les deux sens, uniquement par des contrats `Shared` (requêtes, commandes, événements). |
| Journal d'audit | **Deux rôles PostgreSQL** : `depverify_app` (runtime, `INSERT` / `SELECT` seulement sur le schéma `audit`) et `depverify_owner` (migrations et maintenance des partitions, CLI uniquement). Le journal est non modifiable par l'application ; une preuve d'altération par chaînage est un non-objectif. |
| UI de la console | **Listes en DataTables côté serveur** (pagination, tri et recherche passent par le bus de requêtes) ; **Turbo Frames lazy** avec placeholder pour les zones lourdes qui ne sont pas des listes (jauges de quota, journal d'audit) ; **Turbo Stream** après une action, sans rechargement. Pas de temps réel (pas de Mercure). |
| Exécution | **Mode worker FrankenPHP, production comprise** (`FRANKENPHP_LOOP_MAX=500`) : aucun état statique, tout service avec un état implémente `ResetInterface`. |
| Fréquence d'inventaire | **Toutes les 6 h + à la demande** (`SCAN_NOW`), et immédiatement à chaque changement d'image détecté en conteneur. **Historique de 90 jours**, puis seul le dernier état est conservé. Réglable par équipe. |

### Décisions du step 1 de la console (09/11/2026)

Socle Identity, Organization et Audit. Le détail et les tests associés sont dans le plan du step ; ce qui suit est ce qui engage la suite.

**Connexion et comptes**
1. Passkeys reportées au step 1b ; le modèle leur réserve leur place.
2. **Second facteur à chaque connexion, pour tout le monde** : TOTP s'il est configuré, sinon code par email. « Faire confiance à cet appareil » saute le second facteur pendant 30 jours, admins compris, jamais le mot de passe.
3. Perte du TOTP : 10 codes de secours à usage unique (affichés une fois, stockés hachés), ou réinitialisation du 2FA par le super admin (auditée). Une fois le TOTP actif, plus de repli sur le code email.
4. Emails par `MAILER_DSN` (Mailpit en dev, TLS obligatoire en production) ; l'écran SMTP d'InstanceSettings est reporté.
5. Mot de passe de 12 à 4 096 caractères, sans règle de composition, Argon2id, ni égal à l'email ni le contenant ; pas d'appel HIBP.
6. Limitation des échecs en fenêtre glissante, sans verrouillage du compte : mot de passe 5 / 15 min par compte + IP et 50 / 15 min par IP ; code email 5 essais par code et 3 renvois / 15 min ; second facteur 5 échecs / 15 min et 20 / 24 h par compte (avec email d'alerte au titulaire). Tout passe par `symfony/rate-limiter`, en échec fermé.
7. Sessions en PostgreSQL : 30 min d'inactivité, 12 h au total, cookie `__Host-` `HttpOnly` / `Secure` / `SameSite=Strict`, pas de « remember me ».
8. Ré-authentification (mot de passe puis second facteur) au-delà de 10 min pour : mot de passe, TOTP et codes de secours, `ROLE_SUPER_ADMIN`, réinitialisation du 2FA d'un autre compte, désactivation d'un compte.
9. Mot de passe oublié : même réponse que le compte existe ou non, lien à usage unique de 30 min, 2FA toujours exigé ensuite, sessions et appareils de confiance révoqués.
10. Emails d'alerte au titulaire (changement de mot de passe, TOTP activé ou désactivé, codes régénérés, 2FA réinitialisé, `ROLE_SUPER_ADMIN` accordé ou retiré, nouvel appareil de confiance), sans lien d'action.
11. Comptes « notification seule » : de vrais `User` sans `account.login` ; ce step livre le modèle et le refus de connexion, le reste vient avec le contexte Notification.

**Équipes, rôles et quotas**
12. Le premier `TEAM_ADMIN` est choisi à la création de l'équipe (autocomplétion sur les comptes de l'instance) et **admis directement**, sans invitation à accepter : un compte existant reçoit un email d'alerte ; un email inconnu crée le compte par invitation (lien de création de 7 jours) dans la même transaction. Un compte désactivé, supprimé ou « notification seule » est refusé, et rien n'est créé. L'équipe garde ensuite au moins un `TEAM_ADMIN` actif (les équipes créées avant cette règle restent sans admin jusqu'à l'acceptation de leur invitation).
13. Ordre des rôles : `TEAM_ADMIN` > `TEAM_MEMBER` > `TEAM_VIEWER` > `TEAM_GUEST` et `PROJECT_ADMIN` > `PROJECT_MEMBER` > `PROJECT_VIEWER` ; on peut attribuer un rôle égal au sien ; un `TEAM_ADMIN` couvre tous les rôles projet de son équipe ; un `TEAM_MEMBER` compte comme `PROJECT_MEMBER` dans les projets de son équipe (décision du 11/11/2026) ; un `PROJECT_ADMIN` ne touche jamais aux rôles d'équipe et ne retire jamais d'un projet un membre de l'équipe (`TEAM_MEMBER` ou plus) : seul un `TEAM_ADMIN` le peut.
14. Invitation sur un projet sans être dans l'équipe : l'acceptation crée aussi une TeamMembership `TEAM_GUEST`. Invitation de 7 jours, renvoyable (3 / h par invitation, 30 / h par équipe) et révocable ; quota `maxMembers` vérifié à l'envoi et à l'acceptation.
15. Quotas : le super admin est bloqué lui aussi (corrige §5ter et §7bis).
16. Suppressions : comptes désactivés, jamais supprimés ; projet ou environnement supprimé seulement s'il est vide ; **équipe supprimée en cascade** par le super admin (`team.delete`, confirmation simple depuis `/admin/teams`) : ses projets, environnements et adhésions partent avec elle, ses invitations en attente sont révoquées, l'historique des droits et le journal d'audit restent ; effacement RGPD reporté.

**Audit et exécution**
17. L'audit enregistre les commandes métier (succès et échec), les refus d'accès (404 et 403) et les événements d'authentification, pas les lectures réussies. Une création est auditée **sur son parent** (projet sur l'équipe, environnement sur le projet), pour qu'un refus garde la portée de l'équipe.
18. `audit.audit_log` partitionnée par mois, triggers qui refusent `UPDATE`, `DELETE` et `TRUNCATE`, purge par détachement des partitions plus anciennes que `AUDIT_RETENTION_DAYS` (365 jours).
19. Mode worker FrankenPHP en production ; connexions hors bus avec délais de session (`lock_timeout`, `statement_timeout`).
20. UI en anglais via le translator ; listes en DataTables, zones lourdes en Turbo Frames lazy, Turbo Stream après une action.

**Risques acceptés**
- Un super admin sans TOTP : sa boîte mail devient le seul facteur (réinitialisation, code, appareil de confiance). Compensé par les emails d'alerte et un bandeau « TOTP recommandé ».
- L'audit de l'authentification échoue ouvert : une écriture d'audit en échec est journalisée sans bloquer la connexion.
- Qui connaît un mot de passe peut bloquer le second facteur de ce compte pendant 24 h, et, derrière un NAT, la fenêtre IP du second facteur des collègues pendant 15 min.
- L'identifiant de session est stocké brut en base (borné à 12 h, révocable par `authVersion`, table réservée au rôle runtime).

### Décisions du step 2 de la console : Fleet (11/11/2026)

Cœur de Fleet, sans installeur (`install.sh` et miroir des binaires attendent une release de l'agent) ni inventaire. Le détail est dans le plan du step ; ce qui suit engage la suite.

**Jetons et enrôlement**
21. Jeton `dvet_` + 43 caractères base64url (256 bits), stocké haché (HMAC + pepper), affiché une seule fois, jamais audité.
22. Jeton **à usage unique** : valable **1 heure**, 1 agent, consommé au premier enrôlement réussi ; rien à régler. Jeton **réutilisable** : environnement par défaut, expiration (90 jours au plus) et nombre maximal d'agents (1 à 10 000) obligatoires ; `pending → approved → revoked`. Seuls les enrôlements faits **après** sa validation donnent des agents `approved`.
23. Quota `maxAgents` : compte les agents `pending` et `approved` (un jeton inutilisé ne réserve pas de place) ; il bloque la création de jeton et l'enrôlement (`quota_exceeded`, 409), et la validation d'un agent si l'équipe est au-dessus de sa limite. `maxReusableEnrollmentTokens` compte les jetons réutilisables actifs (ni révoqués, ni expirés, ni épuisés). Tout comptage se fait sous un verrou de flotte par équipe (`fleet.team:<id>`), y compris l'effacement d'une équipe supprimée.
24. Hôte créé ou retrouvé à l'enrôlement, par équipe : moteur Docker pour un agent conteneur, machine-id pour un agent hôte, chacun se rabattant sur l'autre puis sur le nom d'hôte. Un ré-enrôlement (volume perdu) crée un nouvel agent sur le même hôte. Un hôte se supprime quand tous ses agents sont révoqués (il emporte ces agents et leurs ordres).
25. Modes acceptés : `host`, `container` (portées `compose`, `labeled`, `host`) et `embedded` (sans portée) ; `ecs` répond `invalid_payload`. Un agent `embedded` est son propre hôte (identité : l'empreinte de sa clé, une réplique = un agent = un hôte), lit son système de fichiers (paquets OS, dont rpm par les lecteurs de bases sans commande, runtimes de la liste fixe, applications des racines de découverte et de `/app`, `/usr/src/app`), n'envoie que ses sujets `host` et `path` (sinon `scope_violation`) et refuse `UPGRADE_AGENT` (il suit l'image).
26. Un environnement par défaut d'un jeton utilisable ne peut pas être supprimé. Une équipe supprimée emporte sa flotte (ordres, agents, hôtes, jetons) dans la même transaction ; ses agents reçoivent ensuite `unknown_agent` et s'arrêtent.

**Agents et protocole**
27. Statuts `pending`, `approved`, `inactive` (7 jours sans requête valide ; la suivante le réactive si le quota le permet), `revoked` (définitif : une nouvelle installation, donc une nouvelle clé, est nécessaire). Refuser un agent en attente, c'est le révoquer. Un agent `inactive` depuis 30 jours de plus est **révoqué** plutôt que supprimé : son historique et l'audit restent.
28. Clé de la console : `APP_AGENT_SIGNING_KEY` (graine Ed25519 en base64), en échec fermé hors dev et test ; en changer impose de réinstaller tous les agents.
29. Vérification des requêtes dans l'ordre du protocole §4.3 par un pare-feu sans session (`^/agent/v1`) ; l'enrôlement vérifie lui-même la preuve de possession. `@target-uri` est reconstruit depuis la requête : derrière un proxy, `SYMFONY_TRUSTED_PROXIES` est requis. Jamais de redirection ni de page HTML sous `/agent/v1` : toute erreur est un `application/problem+json`.
30. Limites : 60 requêtes / min par agent, comptées **après** vérification de la signature (un `keyid` forgé n'épuise pas la fenêtre d'un agent) ; 20 enrôlements / h par IP (force brute sur les jetons). `next_poll_in` : 60 s en attente, 300 s une fois validé ; pas encore de long polling.
31. Audit : enrôlements, gestes de l'interface et refus de requêtes agent (endpoint, `keyid` annoncé, raison, IP ; jamais le corps). Un poll ordinaire n'écrit rien (une entrée toutes les 5 min par agent noierait le journal).

**Ordres**
32. Cycle `queued → delivered → executed | failed | rejected`, `expired` 60 s après l'échéance sans résultat, `cancelled` à la révocation de l'agent. Signé à la première livraison (`issued_at = now`, `expires_at = +15 min`), relivré avec la même signature jusqu'à son résultat ; un ordre expiré n'est jamais relivré. Au plus 20 ordres par réponse.
33. `SCAN_NOW` : 1 par agent toutes les 5 minutes. `SET_CONFIG` : configuration souhaitée par agent, `config_version` croissante, intervalle jamais sous le `minScanIntervalMinutes` de l'équipe ; un `SET_CONFIG` pas encore signé est annulé par le suivant, et le poll remet en file la configuration d'un agent qui rapporte une version inférieure.
34. Maintenance `app:fleet:maintain` (cron, par lots) : agents inactifs, révocation des inactifs anciens, ordres expirés, nonces de plus de 10 minutes.

### Décisions du step 3 de la console : Inventory (11/11/2026)

Réception, stockage et normalisation des inventaires envoyés par l'agent (protocole §8), et leur affichage. Ni matching, ni diff entre inventaires, ni sources Git / CI / upload. Le détail est dans le plan du step.

**Protocole et réception**
35. Sujet `kind: host` (paquets OS de l'hôte, `subject_key: host`), envoyé par un agent `host` ou un agent `container` en portée `host`, jamais en portée `compose` / `labeled`. Le SBOM n'a **pas de `serialNumber`** : un identifiant changeant à chaque inventaire changerait le digest d'un contenu identique et annulerait la déduplication.
36. Snapshots stockés dans PostgreSQL (`bytea` gzip), **dédupliqués par (équipe, digest)** : une équipe n'apprend jamais qu'une autre détient un document. `inventory_id` choisi par l'agent ; rejouer le même manifeste est idempotent ; le même id venant d'un autre agent est `invalid_payload`.
37. Garde de portée vérifiée **dès le manifeste** (rien n'est stocké) et à `complete` : en portée `compose` / `labeled`, seuls les services du projet Compose enrôlé et leurs images ; un écart rejette tout l'inventaire (`403 scope_violation`, audité). Un agent en attente reçoit `403 agent_pending` sur les trois endpoints.
38. Envoi d'un snapshot : 20 Mio compressés au plus (limite par route, aussi dans Caddy), décompression en flux arrêtée à 200 Mo (`payload_too_large`), SHA-256 des octets décompressés égal au digest (`422 digest_mismatch`), format vérifié (CycloneDX 1.6 dont `metadata.component.bom-ref` = `subject_key`, faits d'hôte `format_version` 1).
39. `complete` : `409 missing_snapshots` (liste des digests) tant qu'il en manque, sinon `202` et un message `ProcessInventory` dans la file asynchrone `ingest` (transport Doctrine, service `worker`). L'API ne parse rien d'autre. Audit : le manifeste, le `complete` et le traitement, jamais chaque envoi de snapshot.

**Traitement**
40. Un sujet `path`, `compose_service` ou `container` devient une **application** (AppInstance) d'identité (hôte, `subject_key`) ; un `container_image` une image d'identité (équipe, `image_id`) ; un `host` le SBOM OS de l'hôte. Les paquets d'un SBOM sont extraits **une fois par blob** (purl, écosystème, nom, version, direct ou transitif, gestionnaire). Une application absente du dernier inventaire de l'agent qui la rapporte devient `gone` et garde son historique ; plusieurs agents sur un même hôte ne se l'enlèvent pas.
41. Rattachement automatique : label `dev.depverify.environment` s'il désigne un environnement de l'équipe, sinon l'environnement par défaut du jeton si l'hôte ne porte qu'une application, sinon « non rattachée ». Un rattachement ou un détachement manuel (`project.apps.assign`, sur le projet cible **et** sur le projet actuel) n'est jamais écrasé. L'équipe de l'environnement est celle de l'application : vérifié par le handler et par un trigger PostgreSQL.
42. Historique : un enregistrement par sujet et par inventaire, purgé au-delà de `snapshotRetentionDays` en gardant le dernier de chaque sujet ; blobs orphelins supprimés ; inventaires non complétés en 1 h abandonnés. Commande `make inventory-maintain` (cron).

**Visibilité**
43. Un membre de l'équipe (hors `TEAM_GUEST`) voit toutes les applications, hôtes et images. Un `TEAM_GUEST` voit les applications rattachées aux projets qu'il voit, et les hôtes et images qui les portent (faits, paquets OS) ; jamais les applications non rattachées ni celles des autres projets (404), ni Hosts / Agents / Enrollment (403). Une équipe supprimée emporte son inventaire ; un environnement portant des applications ne se supprime pas.

### Décisions du step 4 de la console : Vulnerability et Exposure (12/11/2026)

Synchronisation des sources publiques, matching local et Findings, avec l'acceptation de risque et leur affichage sur les pages application et hôte. Ni dashboards (step 5), ni notifications (step 6). Le détail est dans le plan du step.

**Sources et confidentialité**
44. OSV par l'**API ciblée** (`/v1/querybatch`, puis `/v1/vulns/{id}` pour les seules advisories nouvelles ou modifiées), pas par les exports complets : seuls les paquets réellement inventoriés sont surveillés. osv.dev ne reçoit **que des couples (écosystème, nom)**, jamais une version, un hôte ni une équipe ; endoflife.date, Packagist et npm que des noms de produits ou de paquets ; FIRST que des CVE. Les versions se comparent localement. Le mode hors ligne (§11) devra ajouter un import.
45. Protocole v1, ajout additif (§8.5) : un paquet OS porte `distro` (`debian-12`) et, quand il diffère du binaire, `upstream` (paquet source, comme syft) ; les advisories des distributions nomment les paquets sources (`openssl`, pas `libssl3`). Sans `distro`, un paquet OS n'est pas évalué (compté, jamais deviné). Écosystèmes OSV suivis : Packagist, npm, `Debian:N`, `Ubuntu:X.Y[:LTS]`, `Alpine:vX.Y`, `AlmaLinux:N`, `Rocky Linux:N`, RHEL (décisions 73 et 80) et SUSE / openSUSE (décision 81).
46. Une comparaison de versions par écosystème, dans le Domain : Composer (`composer/semver`), SemVer 2 (npm), dpkg (Debian, Ubuntu), apk (Alpine), rpmvercmp (RPM). Une version illisible ne produit aucun Finding. Plages OSV évaluées selon le schéma (`introduced`, `fixed`, `last_affected`, `limit`, liste `versions`) ; les plages `GIT` sont ignorées. Score CVSS 3.x calculé depuis le vecteur ; un vecteur CVSS 4 est gardé sans score et la sévérité vient alors de la base (`MODERATE` = medium). KEV (catalogue CISA complet) et EPSS (FIRST) sont stockés par CVE.
47. Fins de vie (endoflife.date) : runtimes PHP et Node (faits d'hôte, runtime de l'application), OS de l'hôte (faits) ou de l'image (`distro` de ses paquets), Symfony, Laravel et Drupal. Une version appartient au plus long cycle qui la préfixe. Niveaux `upcoming` (J-180), `soon` (J-90), `imminent` (J-30), `expired`, recalculés chaque jour. **Un Finding par cycle** (un hôte peut faire tourner Node 20 et 22).
48. Obsolescence : dépendances **directes** Composer et npm seulement, contre la dernière version stable (Packagist `p2`, `latest` de npm) ; retard majeur ou mineur, jamais un retard de correctif seul.

**Findings**
49. Un Finding porte sur une **application** (les paquets de son image comptent pour elle) ou sur un **hôte** (OS, runtimes, paquets OS). Identité : (équipe, sujet, type, clé) avec la clé advisory + paquet, produit + cycle, ou paquet. Il est ouvert tant que le matching le produit, corrigé sinon (jamais supprimé), rouvert s'il revient avec sa date de première détection. Événements d'ouverture et de correction publiés pour les notifications.
50. Recalcul **par équipe**, idempotent, dans la file `matching` ; les appels externes dans la file `feeds`. Déclencheurs : chaque inventaire traité, chaque advisory modifiée, un recalcul quotidien. Une demande de recalcul déjà en attente pour l'équipe n'en ajoute pas une autre : une synchro de centaines d'advisories ne recalcule chaque équipe qu'une fois.
51. Planification : des commandes et leurs cibles (`make vuln-sync` toutes les 6 h, `make eol-sync` puis `make findings-refresh` chaque jour), sans bundle cron pour l'instant ; elles ne font que mettre le travail en file.

**Acceptation de risque et visibilité**
52. Accepter un risque exige une justification (2000 caractères au plus) et une date d'expiration après aujourd'hui et dans l'année ; une acceptation en cours est remplacée, révocable, et expire d'elle-même (le Finding redevient ouvert, sans tâche dédiée). Auditée (date d'expiration seulement, la justification est du texte libre). Permissions : `finding.accept_risk` sur le projet de l'application ; pour un hôte ou une application non rattachée, qui relèvent du parc, `host.approve` (une permission de projet n'a pas de sens sans projet).
53. Visibilité : les Findings d'une application rattachée suivent son projet ; ceux d'un hôte ou d'une application non rattachée ne sont vus que par qui voit tous les projets de l'équipe (pas un `TEAM_GUEST`, 404). Une équipe supprimée emporte ses Findings et leurs acceptations.

### Décisions du step 5 de la console : dashboards (12/11/2026)

Dashboards par équipe, projet, environnement et hôte, et liste filtrée des Findings. La matrice des composants par environnement (§5bis) suit au step 7.

54. Un Finding **copie l'emplacement de son sujet** à chaque recalcul : nom de l'application ou de l'hôte, environnement et projet d'une application rattachée. Les dashboards et les listes filtrent en SQL dans Exposure, sans appeler un autre contexte par ligne. Un rattachement ou un détachement manuel publie `ApplicationPlacementChanged`, qui recalcule l'équipe (coalescé comme le reste).
55. Chiffres d'un périmètre : Findings ouverts **non acceptés** par sévérité (KEV à part), fins de vie par niveau, dépendances en retard, acceptés à part ; ouverts et corrigés par jour sur 30 jours ; les 5 applications les plus exposées (KEV, puis critiques, puis hautes) ; le calendrier des fins de vie avec le **cycle conseillé** (le plus récent encore supporté, « PHP 8.2 → 8.5 »).
56. Graphiques Chart.js via `symfony/ux-chartjs`, coloriés depuis le thème au moment du rendu (aucun attribut `style`, la CSP reste stricte). Les chiffres sont toujours écrits à côté : le graphique illustre, il ne porte pas l'information seul.
57. Pages : section **Findings** de l'équipe et du projet (dashboard, puis liste filtrable par type, sévérité, statut, projet ou environnement, filtres dans l'URL) ; **page d'un environnement** (dashboard, applications, Findings) ; frames de synthèse sur les vues d'ensemble de l'équipe et du projet et sur la page hôte. Un `TEAM_GUEST` voit les Findings de ses projets, jamais ceux du parc.

### Décisions du step 6 de la console : notifications (13/11/2026)

Email et webhook signé, règles par projet et par parc, digests, agents muets, acceptations qui expirent, destinataires « notification seule ». Slack, Teams, Discord et la création de tickets viennent plus tard. Le détail est dans le plan du step.

**Événements et envoi**
58. Notification ne lit jamais les tables des autres contextes : Exposure publie `FindingChanged` (ouvert, rouvert, corrigé, fin de vie qui se rapproche, avec la date de l'occurrence), Fleet `AgentAwaitingApproval` ; les détails passent par les contrats `GetFindingDigests`, `ListSilentAgents`, `ListExpiringAcceptances`, `FilterRecipients`. Un Finding dont le risque est accepté reste silencieux.
59. **Outbox** : une `Notice` par règle et par occurrence (index unique), avec un instantané de ce qu'elle dit ; une `Delivery` par destinataire (index unique). Un événement traité deux fois n'est dit qu'une fois. Les essais d'une livraison immédiate sont comptés par l'entité (1, 5, 25 puis 125 minutes, échec au 5ᵉ), jamais par Messenger : un essai raté n'est pas annulé par un rollback. File Messenger `notifications`.
60. **Règle** : un projet (éventuellement un seul environnement) ou le **parc** de l'équipe (hôtes, applications non rattachées, agents). Événements : vulnérabilité trouvée ou corrigée, fin de vie, version en retard, agent muet, agent à approuver, acceptation qui expire ; les agents ne concernent que le parc. Seuils réservés aux vulnérabilités, tous exigés : sévérité, CVSS, EPSS minimaux, KEV seulement. Silence d'un agent réglable (24 h par défaut). Un projet peut n'avoir aucune règle.
61. **Destinataires** : les webhooks de la règle (toujours immédiats) et, si elle le dit, les abonnés de son périmètre par email, chacun à sa fréquence (immédiat, digest quotidien, digest hebdomadaire le lundi, ou rien). Au moment de l'envoi, on vérifie encore que le destinataire est actif, toujours abonné et voit toujours le périmètre (ses memberships, jamais son statut de super admin) ; sinon la livraison est abandonnée.
62. **Webhook** : URL HTTPS sans identifiants, secret HMAC chiffré (`SecretBox`, lié au webhook) et montré une seule fois, `POST` d'un JSON versionné signé `sha256=HMAC(secret, timestamp.body)` (`docs/webhook.md`). Jamais de redirection suivie ni de réseau privé (`NoPrivateNetworkHttpClient`, levé en dev par `NOTIFICATION_WEBHOOK_ALLOW_PRIVATE=1`). Le dernier appel (succès ou erreur courte) est affiché ; bouton « Tester ».
63. **Email** : envoyé directement par le worker ; lien de désinscription signé (`UriSigner`, sans connexion), en-têtes RFC 8058 ; un `GET` ne fait que demander, le `POST` coupe l'abonnement.
64. Planification : `make notifications-check` toutes les 5 minutes (agents muets une fois par période de silence, acceptations qui expirent sous 7 jours une fois, relance des livraisons dues) et `make notifications-digest` chaque jour à 07:00.

**Comptes « notification seule » (décision 16)**
65. Un gestionnaire (`project.notifications.manage`) ajoute une **adresse** : il ne crée qu'une invitation dans Notification (lien haché de 7 jours), **sans compte ni membership**, avec la même réponse quelle que soit l'adresse (ni accaparement d'adresse, ni énumération des comptes). À la confirmation (un `POST` sur le lien, preuve de possession de la boîte) : Identity crée ou réutilise le compte « notification seule » ; Organization l'admet `PROJECT_VIEWER` (et `TEAM_GUEST`) au nom du gestionnaire, s'il a toujours la permission. Une adresse d'un compte qui se connecte n'est jamais rattachée ainsi : abonnée si elle voit déjà le projet, sinon l'invitation est déclinée (à inviter au projet). Quota `maxNotificationOnlyAccounts` : adresses invitées et comptes rattachés, chacun une fois.
66. Un compte « notification seule » est **promu** en compte complet en acceptant une invitation (il choisit son mot de passe) ou en devenant premier `TEAM_ADMIN` (lien de création), sans perdre ses memberships.

### Décisions de l'agent v0.1 (13/11/2026)

Protocole v1 complet (enrôlement, polling signé, ordres `SCAN_NOW` et `SET_CONFIG`, inventaires), modes `host` et `container`, vérifiés de bout en bout contre la console. Le détail est dans le `CLAUDE.md` du dépôt de l'agent.

67. **Agent synchrone**, sans runtime async : une boucle (poll, ordres, inventaire). HTTP vers la console avec `ureq` (rustls) ; l'API Docker par un mini-client HTTP en lecture seule (TCP vers le proxy, ou socket Unix), réponses lues en flux. Pas de `bollard` ni de `tokio` : un binaire statique de 4 Mo.
68. Racines TLS : celles de Mozilla embarquées dans le binaire (l'image `scratch` n'a pas de magasin système), ou une CA privée par `AGENT_CA_FILE` ; `HTTPS_PROXY` respecté.
69. Inventaire d'une image : export `GET /images/{id}/get` lu couche par couche (formats Docker et OCI, compressé ou non), seules les bases de paquets gardées, whiteouts appliqués ; cache par Image ID et version de l'agent. Les dépendances d'une application conteneurisée viennent du conteneur en cours (`GET /containers/{id}/archive`), aux chemins des labels ou aux emplacements usuels. Les bases RPM des images sont lues sans `rpm`, en Rust pur : SQLite (`rpmdb.sqlite`, RHEL 9, Fedora, Amazon Linux 2023), ndb (`Packages.db`, SUSE et openSUSE) et Berkeley DB (`Packages`, RHEL 7 et 8).
70. Code de sortie 3 = arrêt définitif (agent révoqué ou inconnu, jeton refusé, clé de console différente) : l'unité systemd ne le relance pas en boucle (`RestartPreventExitStatus=3`).
71. **Releases et `install.sh`** : un tag `vX.Y.Z` de l'agent publie une GitHub Release (binaires statiques x86_64 et aarch64, `SHA256SUMS` signé minisign par la clé de release du projet, secret de CI). La console télécharge la dernière release chaque jour (`make agent-release-sync`, ou import manuel d'un dossier pour une instance sans Internet), vérifie la signature avec `AGENT_RELEASE_PUBKEY` (clé de release du projet, minisign, id `EBDDB456A4BF3356` : `RWRWM7+kVrTd63TMnDIUOLjb78MC3QJTImbW3Gi/8ooaxK7iF2tC/ZSz`, valeur par défaut commitée de la console) et chaque binaire contre ses sommes, puis seulement les sert (`/downloads/agent/…`). `/install.sh` est généré à la demande : URL et clé de la console, version et SHA-256 de chaque architecture ; sans release vérifiée, il refuse (503). Le dialogue du jeton donne la commande `curl --proto '=https' --tlsv1.2 -fsSL …/install.sh | sudo AGENT_TOKEN=… sh`.
72. **Image officielle** : un tag `vX.Y.Z` du dépôt `agent-image` construit `ghcr.io/dependencyverifier/agent:X.Y.Z` (amd64, arm64) **à partir des binaires de la release signée**, vérifiés pendant le build comme la console les vérifie (signature minisign, version du commentaire signé, SHA-256), sans recompiler ; l'image est poussée avec ses attestations de provenance et de SBOM, puis signée cosign sans clé (OIDC GitHub).

### Décisions du step 7, findings en contexte et production d'abord (13/11/2026)

73. **Avis RHEL** : OSV publie les RHSA de Red Hat par flux (`Red Hat:enterprise_linux:9::appstream`, `…::baseos`, `…::crb`), en nommant les **paquets binaires** (pas les sources) avec des versions `epoch:version-release` (époque 0 écrite). La console ramène les flux d'une version majeure à une clé (`Red Hat:enterprise_linux:9`), interroge OSV sur la famille `Red Hat` (seule réponse de l'API) et garde le nom binaire d'un paquet `distro=rhel-N` (pas `upstream`). Les canaux de mise à jour (EUS, E4S / SAP, AUS, TUS) et RHEL 10 : décision 80 ; les autres produits Red Hat (EUS long life, ELS, NVIDIA, OpenShift…) ne sont pas suivis.
74. **Production d'abord** : un Finding copie aussi l'hôte de son sujet et s'il est en production — une application dans un environnement marqué production, un hôte qui en porte une. Changer le drapeau d'un environnement relance le calcul. La liste des Findings se filtre par hôte (l'hôte et ses applications) et par production ; le tableau de bord d'équipe ouvre sur la production (exploitées, critiques, élevées, fins de vie, les 5 plus urgentes) ; l'accueil rassemble la production de toutes les équipes de l'acteur (un super admin : les siennes).
75. **Matrice d'un environnement** (§5bis) : par composant (runtime, OS de l'image ou de l'hôte, dépendances directes), chaque version et les applications et hôtes qui la portent ; plusieurs versions d'un même composant = dérive, filtrable.
76. **Page d'un avis** (`/teams/{id}/advisories/{id OSV ou alias}`) : l'avis tel que synchronisé (textes toujours échappés, références en liens sortants jamais suivis) et les Findings de l'équipe qu'il cause ; les identifiants d'un Finding y mènent, osv.dev en lien secondaire.
77. **Runtime d'une application (mode host)** : le pool PHP-FPM auquel son serveur web la confie (pools Debian, RHEL et Remi ; sites nginx et Apache, lus dans leurs fichiers, jamais par une commande), avec sa version et son service (`php8.2-fpm`) ; à défaut, le `php` par défaut de l'hôte.
78. **`UPGRADE_AGENT`** (mode `host`) : la console met en file la dernière release vérifiée pour un agent hôte en retard (bouton sur la page de l'agent, ou pour tous ceux de l'équipe), un ordre en attente à la fois ; elle sert aussi `SHA256SUMS` et sa signature. L'agent télécharge la release, vérifie la signature avec la **clé de release embarquée**, la version signée et le SHA-256, la garde dans son dossier d'état (`bin/X.Y.Z/`) puis s'exécute dessus ; à chaque démarrage, le binaire installé revérifie la release avant de lui céder la place. Aucun privilège en plus (l'unité systemd est inchangée) ; un agent conteneur se met à jour par son image.
79. **Rotations de clés.** `ROTATE_KEY` : l'agent génère une nouvelle paire, l'annonce par `POST /agent/v1/key-rotations` signé par l'ancienne clé avec une preuve signée par la nouvelle (protocole §5.3) ; la console vérifie l'ordre, la preuve et l'unicité, puis remplace la clé (audité). L'ancienne clé reste chez l'agent jusqu'à la première requête acceptée avec la nouvelle (reprise après coupure). `ROTATE_CONSOLE_KEY` : chaque agent épingle une clé de console (`console_key_id`, renseignée au premier poll) et chaque ordre est signé avec la clé épinglée par son agent. **Procédure** : (1) générer une graine (`openssl rand -base64 32`) dans `APP_AGENT_SIGNING_KEY_NEXT` ; (2) `make console-key-rotate` envoie la nouvelle clé, signée par l'ancienne, à chaque agent approuvé ; (3) le relancer jusqu'à 100 % (les agents enrôlés entre-temps épinglent encore l'ancienne) ; (4) mettre la nouvelle graine dans `APP_AGENT_SIGNING_KEY` et vider `APP_AGENT_SIGNING_KEY_NEXT` (`install.sh` et l'enrôlement donnent alors la nouvelle clé). Un agent resté sur une clé que la console n'a plus ne reçoit plus d'ordre : il faut le réinstaller.
80. **Canaux Red Hat et RHEL 10** : OSV publie RHEL 10 par version mineure (`Red Hat:enterprise_linux:10.1`), ramenée à sa version majeure comme les flux (les mineures du flux principal se suivent), et chaque canal par version mineure : `Red Hat:rhel_eus:9.4::baseos`, `rhel_e4s` (Update Services for SAP Solutions), `rhel_aus`, `rhel_tus`, `enterprise_linux_eus:10.0` pour RHEL 10, ramenés à une clé `Red Hat:eus:9.4`. L'agent lit le canal **dans des fichiers seulement** : le dépôt BaseOS activé de `/etc/yum.repos.d/redhat.repo` (écrit par subscription-manager ; `…-baseos-eus-rpms`) et la version verrouillée de `/etc/dnf/vars/releasever`, sinon `VERSION_ID`. Il l'envoie dans le qualifier `channel` des paquets rpm, avec `distro=rhel-9.4` (la mineure est gardée pour RHEL). Un hôte d'un canal n'est comparé qu'aux builds de ce canal (ceux du flux principal donneraient de faux positifs) ; un canal sans version mineure n'est pas évalué. Les images (UBI) n'ont pas ces dépôts : flux principal. Les avis Red Hat déjà stockés sont relus une fois (migration).
81. **SUSE et openSUSE** : OSV publie SUSE Linux Enterprise par produit et par module (`SUSE:Linux Enterprise Server 15 SP6`, `…-LTSS`, `… for SAP Applications 15 SP6`, `SUSE:Linux Enterprise Module for Basesystem 15 SP7`…), en nommant les **paquets sources** (`openssl-3`), versions rpm sans époque. La console ramène le serveur, son édition SAP, ses modules et LTSS d'un service pack à une clé `SUSE:sle:15.6` (`distro=sles-15.6`, SLES for SAP compris), Micro à `SUSE:micro:6.1` (`sl-micro-6.1`, `sle-micro-5.5`), et garde `openSUSE:Leap 15.6` (`opensuse-leap-15.6`) et `openSUSE:Tumbleweed` (`opensuse-tumbleweed`, sans version). L'API ne répond qu'aux familles : `SUSE` pour SLE, Micro et Leap 15, `openSUSE` pour Tumbleweed et Leap 16. Non suivis : HPC, Manager, Desktop, Leap Micro. Fins de vie : produits endoflife.date `sles` et `opensuse` (Leap) ; Tumbleweed n'en a pas.

## 4. Architecture d'ensemble

```
 Serveur supervisé                               Instance self-hosted   
┌──────────────────────────┐                ┌──────────────────────────────────┐
│  depverify-agent (Rust)   │   HTTPS sortant│  Console                         │
│  - user système dédié    │ ─────────────► │  - API agents (signée)           │
│  - lit lockfiles, dpkg,  │  requêtes      │  - UI web (équipes/projets)      │
│    runtimes, Docker (RO) │  signées Ed25519│ - Workers (Messenger)            │
│  - SBOM CycloneDX        │ ◄───────────── │      · sync OSV / EOL / KEV / EPSS│
│  - aucun port ouvert     │  ordres signés │      · matching vuln ↔ inventaire │
└──────────────────────────┘  (polling)     │      · notifications / digests   │
                                            │  - PostgreSQL                    │
                                            └──────────────┬───────────────────┘
                                                           │ sortant (téléchargement seul)
                                     OSV.dev · endoflife.date · CISA KEV · EPSS · Packagist/npm
```

**Principe clé :** l'agent ne fait **que de l'inventaire**. Le matching avec les vulnérabilités se fait **côté console**. Quand une nouvelle CVE est publiée, la console recalcule l'exposition de tous les inventaires stockés **sans attendre** le prochain passage des agents.

## 5. Modèle de données (première ébauche)

> **Identifiants : UUID partout.**
> - Toutes les entités (User, Team, Project, Environment, Host, Agent, AppInstance, ContainerImage, Snapshot, Finding, AgentOrder, Invitation, AuditLog…) ont une clé primaire **UUID v7** : ordonnée dans le temps, donc efficace pour les index B-tree. Elle est générée avec `symfony/uid` et stockée en type `uuid` natif PostgreSQL.
> - Aucun identifiant auto-incrémenté n'est exposé : URLs, API, payloads agent et webhooks utilisent l'UUID.
> - Les noms et slugs sont **purement affichés**. Les renommer ne casse aucune référence, et rien ne s'y rattache techniquement.
> - L'agent est identifié par son UUID **et** l'empreinte de sa clé publique.

- **InstanceSettings** (singleton, géré par le super admin) : paramètres SMTP, sources de données, rétention de l'audit, et **quotas par défaut** des équipes. À la création d'une équipe, ces valeurs sont **copiées** dans l'équipe, puis le super admin peut les ajuster. Modifier les quotas par défaut n'affecte pas les équipes déjà créées.
- **User** : email, hash Argon2id (nullable), second facteur (secret TOTP chiffré, nullable ; à défaut, code par email), passkeys (voir PasskeyCredential), statut (`active` ou `disabled`, jamais supprimé), statut de super admin (`isSuperAdmin`, traduit en `ROLE_SUPER_ADMIN` par la sécurité, voir §7bis), permissions d'instance (dont `account.login`), versions de session (`authVersion`, `trustedDeviceVersion`).
  - **Compte complet** : il a la permission d'instance `account.login`, se connecte à la console.
  - **Compte « notification seule »** : un vrai `User` **sans la permission `account.login`**, sans mot de passe. Il reçoit les notifications des projets auxquels il est rattaché, avec un email vérifié par lien de confirmation et un lien de désinscription signé. Un `UserChecker` Symfony refuse toute connexion. Il peut être **promu** plus tard en compte complet par invitation, sans perdre ses rattachements.
- **PasskeyCredential** (appartient à un User, 0..N) : `uuid`, identifiant du credential WebAuthn, clé publique, compteur de signatures, transports, AAGUID, **nom** donné par l'utilisateur (« YubiKey bureau », « iCloud »…), dates de création et de dernière utilisation. Révocable individuellement par son propriétaire (et par le super admin). Enregistrement et révocation tracés dans l'audit.
- **EmailLoginCode** : code à usage unique du second facteur par email, stocké **haché**, expiration courte (~10 min), nombre d'essais limité, invalidé dès usage ou à l'émission d'un nouveau code.
- **Team** : `uuid`, `name`, `slug`, **quotas** (`maxProjects`, `maxAgents`, `maxMembers`, `maxEnvironmentsPerProject`, rétention des snapshots…), initialisés depuis les quotas par défaut de l'instance. Une valeur nulle signifie illimité. Les quotas sont modifiables uniquement par le super admin.
  - **Blocage strict** : toute action qui dépasserait un quota est refusée. C'est le cas de la création d'un projet, d'un environnement, d'un jeton d'enrôlement, de la validation d'un agent ou d'une invitation. Le message d'erreur est explicite et l'admin de l'équipe est invité à contacter le super admin.
  - Si le super admin baisse un quota sous l'usage actuel, rien n'est supprimé, mais toute nouvelle création est bloquée tant que l'équipe est au-dessus de la limite.
- **TeamMembership** (`user`, `team`, `role` : `TEAM_ADMIN` / `TEAM_MEMBER` / `TEAM_VIEWER` / `TEAM_GUEST`, `extraPermissions[]`, `status` : `active` ou `suspended`). Une membership est suspendue quand le compte est désactivé, et restaurée à sa réactivation ; un membre suspendu ne compte ni pour `maxMembers` ni comme `TEAM_ADMIN`. Un utilisateur peut avoir des memberships dans plusieurs équipes.
- **ProjectMembership** (`user`, `project`, `role` : `PROJECT_ADMIN` / `PROJECT_MEMBER` / `PROJECT_VIEWER`, `extraPermissions[]`, `status`). Elle sert aux utilisateurs limités à certains projets d'une équipe.
- **PermissionGrant** (historique) : qui a accordé ou retiré quelle permission, à qui, sur quel périmètre, quand. Aussi tracé dans l'audit.

> **Invariant** : une ProjectMembership exige une TeamMembership dans l'équipe du projet. Retirer quelqu'un d'une équipe supprime ses ProjectMemberships dans cette équipe.
- **Invitation** : email, équipe ou projet cible, rôle, jeton haché à usage unique, émise pour **7 jours** (l'expiration est calculée, jamais stockée), statut `pending` / `accepted` / `revoked`. Une seule invitation en attente par couple email + cible. Toujours un lien à accepter, même si le compte existe déjà.
- **Project** (appartient à une Team) → **Environment**. Le **nom est entièrement libre** (« prod », « recette-client », « staging-eu »…), unique par projet. Un indicateur optionnel `isProduction` permet de durcir les seuils de notification par défaut.
- **Host** (appartient à **une seule** Team) : hostname, OS, distribution, arch, dernière remontée. Il peut porter des AppInstances de plusieurs projets **de la même équipe**.
- **CloudScope** (appartient à une seule Team) : périmètre cloud collecté sans hôte, par exemple un compte AWS + une région + une liste de clusters ECS. Il remplace le Host pour le mode `ecs`.
- **Agent** : clé publique Ed25519, empreinte, **mode** (`host` / `container` / `embedded` / `ecs`), **portée** (pour `container` : `compose` / `labeled` / `host`), statut (`pending` / `approved` / `revoked`), version, `last_seen_at`. Il compte dans le quota `maxAgents` de l'équipe. Rattachement selon le mode :
  - mode `host`, ou `container` en portée `host` : **1-1 à un Host** ;
  - mode `container` en portée `compose` ou `labeled` : **N agents par Host**, un par projet Compose, regroupés via l'ID du moteur Docker ;
  - mode `embedded` : rattaché au conteneur qui l'embarque ;
  - mode `ecs` : à un CloudScope.
- **EnrollmentToken** : **hash** du jeton, Team cible, Environment **par défaut** (optionnel), type, expiration. Il n'est jamais relisible. Deux types :
  - `single` (défaut) : usage unique, expiration ~1 h, agent en `pending` jusqu'à validation humaine ;
  - `reusable` (autoscaling) : `maxUses`, expiration longue mais obligatoire (ex. 90 j max), statut propre (`pending` → `approved` → `revoked`), agents enrôlés validés automatiquement. Il garde la liste des agents enrôlés par lui.
- **AppInstance** : une application déployée, rattachée à **un** Environment. Selon le mode, il s'agit :
  - d'un chemin sur un Host ;
  - d'un conteneur ou service Compose sur un Host ;
  - d'un service ECS (cluster + service + nom de conteneur) dans un CloudScope.

  Autres attributs : source `discovered` ou `declared`, statut de validation, runtime utilisé (ex. le pool `php8.4-fpm` qui la sert), image courante (pour les conteneurs).
- **ContainerImage** : image identifiée par son **Image ID** (`sha256:…`, qui existe aussi pour une image construite localement), avec les `RepoDigests`, registre, dépôt et tags vus quand ils existent, et sa provenance (`registry` / `local-build`). Elle est inventoriée **une seule fois par Image ID** et partagée par toutes les AppInstances qui l'exécutent (voir §6bis).
- **InventorySource** : provenance d'un inventaire. Type `agent` au MVP, puis `git`, `ci`, `upload`. Chaque source est rattachée à une AppInstance ou directement à un Environment (cas Git ou CI, sans hôte).
- **Snapshot** : inventaire horodaté produit par une InventorySource, pour une AppInstance, un Host ou une ContainerImage (SBOM CycloneDX stocké, hash pour la déduplication).
- **Component** : `purl` (ex. `pkg:composer/symfony/http-kernel@6.4.3`), écosystème, nom, version, direct ou transitif.
- **Advisory** : id OSV, alias (CVE, GHSA), résumé, CVSS, plages affectées, versions corrigées, KEV oui/non, score EPSS.
- **EolCycle** : produit (php, nodejs, symfony, debian…), cycle, dates de fin de support actif et de support sécurité.
- **Finding** : (AppInstance ou Host) × (Advisory | EolCycle | Outdated). Statut `open` / `accepted` / `fixed`, dates de première et dernière détection.
- **RiskAcceptance** : Finding, justification, auteur, **date d'expiration obligatoire**.
- **NotificationChannel** : email, webhook (secret HMAC), Slack/Teams/Discord…
- **NotificationRule** (par Project, éventuellement par Environment) : types d'événements, seuil, mode immédiat ou digest, canaux.
- **AgentOrder** : id unique, type, payload, `not_before` / `expires_at`, signature, statut d'exécution.
- **AuditLog** : en ajout seul (voir §7).

> **Invariant** : l'équipe du Host (ou du CloudScope) d'une AppInstance doit être l'équipe du projet de son Environment. Il est vérifié côté applicatif et par une contrainte en base (trigger). Une application ne peut jamais être rattachée à un projet d'une autre équipe que celle de son hôte ou de son périmètre cloud.

## 5bis. Hôtes, agents et projets

### Pourquoi 1 agent = 1 hôte, et pas 1 agent = 1 projet

- Une partie de ce que l'agent inventorie appartient à la **machine**, pas au projet : paquets OS, noyau, versions de PHP/Node installées, images Docker. Avec un agent par projet, un serveur qui porte 3 projets aurait 3 agents qui scannent 3 fois la même chose. Ce serait 3 services systemd, 3 clés et 3 appairages à valider.
- Un agent par projet devrait aussi être **restreint** à ses dossiers. Ça complique les droits système sans gain réel, puisque les projets d'un même hôte appartiennent à la même équipe.

Le cas simple reste simple : **1 serveur = 1 projet**. Le jeton d'enrôlement porte un **environnement par défaut**. Si l'agent ne découvre qu'une application, elle est rattachée automatiquement à cet environnement. Pour l'utilisateur, ça revient à « 1 agent = 1 projet ».

### Hôte multi-projets

Exemple : un serveur `web-01` héberge `/var/www/site-a` (projet A, env « prod ») et `/var/www/api-b` (projet B, env « prod »).

- **Un seul agent** inventorie l'hôte et découvre les 2 applications. Chaque application devient une **AppInstance**.
- L'admin rattache chaque AppInstance à l'environnement de son projet. Ce rattachement est automatique si un chemin déclaré ou l'environnement par défaut du jeton le permet.
- **Les failles d'application** (Composer, npm) sont propres à chaque AppInstance. Elles ne sont visibles que dans le projet concerné.
- **Les failles de l'hôte** (OS, noyau, runtimes) sont **partagées**. Elles s'affichent dans chaque projet présent sur l'hôte, en lecture seule, avec la mention « hérité de l'hôte `web-01` ». Un Finding d'hôte n'est stocké **qu'une fois**. Les notifications sont dédupliquées par destinataire.
- **Plusieurs versions de PHP** sur le même hôte (ex. `php8.2-fpm` et `php8.4-fpm`) : l'agent associe chaque AppInstance au runtime qui la sert, via les pools FPM et les vhosts nginx/Apache. À défaut, il s'appuie sur la contrainte `php` de `composer.json`. Ainsi, le projet A est alerté sur PHP 8.2 et pas le projet B.
- Un utilisateur limité au projet A voit l'hôte `web-01` et ses failles système, mais **jamais** les AppInstances du projet B.

### Projet multi-hôtes

Exemple : le projet A en « prod » tourne sur `web-01`, `web-02` (répartition de charge) et `worker-01`.

- L'environnement « prod » contient 3 AppInstances, une par hôte.
- Le **dashboard de l'environnement** agrège les composants de toutes ses AppInstances. Pour chaque dépendance ou faille, il indique **sur quels hôtes** elle est présente, par exemple « symfony/http-kernel 6.4.3 sur web-01, web-02 ; 6.4.8 sur worker-01 ».
- Une faille sur un seul hôte reste une faille de l'environnement. On ne la notifie **qu'une fois** pour l'environnement, avec la liste des hôtes touchés, et pas une fois par hôte.
- **Détection de dérive** (bonus quasi gratuit avec ce modèle) : signaler quand les hôtes d'un même environnement n'ont pas les mêmes versions, signe d'un déploiement partiel.

### Futures sources sans hôte

Un inventaire venant de Git, de la CI ou d'un upload se rattache **directement à un Environment** (ou à une branche/version), sans Host. Le moteur d'analyse traite toutes les sources de la même manière. La comparaison « ce qui est dans le repo » vs « ce qui tourne en prod » devient alors une simple comparaison entre deux InventorySources du même environnement.

## 5ter. Quotas (validés)

### Quotas par équipe

Ils sont réglés par le super admin pour chaque équipe. Leurs valeurs par défaut sont définies dans InstanceSettings et copiées à la création de l'équipe. Une valeur vide signifie illimité.

| Quota | Ce qui est compté | Défaut | Bloque |
|---|---|---|---|
| `maxProjects` | Projets de l'équipe | 10 | création de projet |
| `maxEnvironmentsPerProject` | Environnements par projet | 3 | création d'environnement |
| `maxAgents` | Agents **actifs** (`pending` + `approved`). Les `inactive` et `revoked` ne comptent pas. | 25 | création d'un jeton, enrôlement, validation |
| `maxMembers` | Comptes **complets** membres actifs de l'équipe (un `TEAM_GUEST` compte) **+ invitations en attente non expirées** | 25 | invitation (à l'envoi et à l'acceptation) |
| `maxNotificationOnlyAccounts` | Comptes « notification seule » rattachés à l'équipe | 50 | ajout d'un destinataire |
| `maxNotificationChannels` | Canaux (webhooks, Slack, Teams…) de l'équipe et de ses projets | 5 | création de canal |
| `maxReusableEnrollmentTokens` | Jetons d'enrôlement réutilisables **actifs** | 3 | création de jeton réutilisable |
| `snapshotRetentionDays` | Durée de conservation de l'historique des inventaires | 90 | *(plafond : l'équipe peut réduire, pas augmenter)* |
| `minScanIntervalMinutes` | Fréquence maximale de l'inventaire automatique : l'équipe peut espacer librement (6 h, 24 h…) mais **pas descendre sous ce plancher** | 60 (1×/heure) | réglage plus fréquent refusé. Le super admin peut l'abaisser pour une équipe, par ex. à 15 min. `SCAN_NOW` reste possible, limité à 1 par agent toutes les 5 min. |

Comportement :
- **Blocage strict à 100 %** : l'action est refusée par le service métier, que la demande vienne de l'UI ou d'un agent, avec un message explicite (« Quota de 25 agents atteint, contactez l'administrateur de l'instance »).
- **Avertissement à 80 %** : bandeau pour les admins de l'équipe et notification optionnelle au super admin. C'est une information, sans blocage.
- Les admins de l'équipe voient leur **consommation** (jauges) dans les paramètres de l'équipe.
- **Le super admin est soumis aux quotas** comme tout le monde : pour dépasser, il relève d'abord le quota de l'équipe (décision du 09/11/2026).
- Une réactivation de compte peut faire dépasser `maxMembers` : rien n'est refusé, comme pour un quota abaissé.
- Si un quota est abaissé sous l'usage actuel, rien n'est supprimé, mais toute nouvelle création est bloquée.

### Limites techniques de l'instance

Ce ne sont pas des quotas d'équipe. Elles sont réglées dans InstanceSettings et protègent la console :

| Limite | Défaut |
|---|---|
| Taille max d'un snapshot (SBOM compressé) | 20 Mo |
| Plancher absolu de `minScanIntervalMinutes` (même pour le super admin) | 5 min |
| Taux de requêtes par agent | 60 / min |
| Rétention du journal d'audit | 365 jours |
| Durée max d'un jeton d'enrôlement réutilisable | 90 jours |
| Agents sans remontée avant passage en `inactive` | 7 jours |
| Révocation des agents `inactive` | 30 jours après passage en `inactive` (décision 27) |

## 6. L'agent

### Langage et distribution

- **Rust**, binaire statique (cible `*-unknown-linux-musl`), `x86_64` et `aarch64`, compilé avec `cargo-zigbuild` ou `cross`.
- Crates pressenties :
  - réseau et crypto : `rustls` (pas d'OpenSSL), `ed25519-dalek`, `minisign-verify` ;
  - analyse des fichiers : `serde_json`, `serde_yaml` ;
  - Docker et format de sortie : `bollard`, `cyclonedx-bom` ;
  - exécution : `tokio`.
- Releases **signées minisign** par la CI du projet, avec un fichier de checksums signé. Images Docker signées cosign.
- Publication **publique sur GitHub** : binaires via GitHub Releases (minisign), image `ghcr.io/dependencyverifier/agent` (cosign). Tout le monde peut les utiliser.
- La console télécharge les releases depuis GitHub (ou les reçoit par **import manuel** d'un binaire signé, pour une instance sans Internet), vérifie leur signature, puis sert `install.sh` et un miroir des binaires vérifiés.
- Plus tard : paquets `.deb` / `.rpm` dans un dépôt signé.

### Installation

```sh
curl -fsSL https://console.example.com/install.sh | AGENT_TOKEN=xxxx sh
```

1. Le jeton passe par une variable d'environnement, pas en argument, pour limiter l'exposition dans `ps` et l'historique. Il est à usage unique et expire en ~1 h.
2. Le script télécharge le binaire, vérifie son SHA-256, crée l'utilisateur système `depverify-agent`, installe l'unité systemd (durcie : `ProtectSystem=strict`, `NoNewPrivileges`, `ReadOnlyPaths`…) et lance l'enrôlement.

### Chaîne de confiance de l'installation

On ne peut pas supposer que `minisign` ou `cosign` est présent sur l'hôte. La confiance repose donc sur 3 maillons :

1. **Clé de release du projet → console.** La CI signe chaque release avec minisign. Avant de servir une version de l'agent, la console télécharge le binaire et vérifie sa signature. Une version non vérifiée n'est jamais servie.
2. **Console → `install.sh`.** Le script est **généré dynamiquement** par la console, en HTTPS, et contient en dur :
   - le **SHA-256 attendu** du binaire, vérifié avec `sha256sum` (coreutils, présent partout) ;
   - la **clé publique de signature de la console**, transmise à l'agent à l'installation. Elle est donc épinglée par un canal de confiance, sans fenêtre de confiance au premier contact.
3. **Agent → mises à jour.** La **clé de release du projet est embarquée** dans le binaire. `UPGRADE_AGENT` vérifie toujours le nouveau binaire avec cette clé, jamais avec celle de la console : une console compromise ne peut pas pousser un binaire arbitraire.

Robustesse du script :
- tout le code est dans une fonction `main` appelée à la **dernière ligne**, pour qu'un téléchargement interrompu n'exécute rien ;
- `set -eu` ;
- recommandation `curl --proto '=https' --tlsv1.2 -fsSL`.

Alternatives pour les plus prudents :
- **dépôt apt/rpm signé** (`signed-by`) ;
- **image Docker signée cosign** ;
- procédure manuelle documentée : télécharger, relire, vérifier minisign, exécuter.

### Enrôlement (appairage)

1. L'agent génère sa paire **Ed25519**. La clé privée reste locale, en `0600`.
2. Il envoie à la console sa clé publique, le jeton et les infos de l'hôte.
3. La console confirme sa clé publique de signature, déjà reçue via `install.sh`. L'agent l'a **épinglée** dès l'installation, comme `known_hosts`. Si elle change ensuite, l'agent refuse tout. Une rotation de clé de la console passe par un ordre signé par l'**ancienne** clé.
4. L'agent passe en statut **`pending`**. Un **admin de l'équipe** (ou toute personne ayant `host.approve` sur l'équipe) doit le **valider manuellement** en comparant l'empreinte affichée des deux côtés. Le super admin n'est pas requis, mais peut aussi le faire. Tant qu'il est en `pending`, ses envois sont refusés et il ne reçoit aucun ordre. **Ce réglage n'est pas désactivable.**
5. La création d'un jeton d'enrôlement et la validation sont refusées si le quota `maxAgents` de l'équipe est atteint.

### Jeton d'enrôlement réutilisable (autoscaling)

Pour les infrastructures qui créent des machines ou des conteneurs seules (ECS sur EC2, groupes d'autoscaling, conteneurs recréés), la validation agent par agent n'est pas tenable. **La validation humaine porte alors sur le jeton, et non sur chaque agent :**

- Un admin (permission `host.enroll`) crée un jeton `reusable`. Il est rattaché à une équipe et à un environnement, avec un **nombre maximal d'agents** et une **date d'expiration obligatoires**. Le jeton est affiché une seule fois.
- Le jeton doit être **validé** par une personne ayant `host.approve`, éventuellement la même. Tant qu'il n'est pas validé, les agents qui l'utilisent restent en `pending`, comme avec un jeton normal.
- Une fois le jeton validé, chaque agent enrôlé avec lui passe directement en `approved`. L'empreinte de l'agent, son hôte et le jeton utilisé sont **tracés dans l'audit**, et une notification « nouvel agent auto-validé » est envoyée selon les règles de l'équipe.
- **Révoquer le jeton** bloque tout nouvel enrôlement. Une option permet de révoquer **en même temps tous les agents** enrôlés avec lui.
- Les agents restent soumis au quota `maxAgents`. À la limite, l'enrôlement est refusé.
- Agents disparus (instance détruite) : après 7 jours sans remontée, ils passent en `inactive` et ne comptent plus dans le quota. Ils sont révoqués 30 jours plus tard (limites d'instance, §5ter ; décision 27).

C'est la **seule** exception à la validation humaine individuelle. Elle est explicite, bornée et tracée.

### Communication

> Spécification normative du protocole agent ↔ console (v1) : [`protocol.md`](protocol.md), avec schémas JSON, exemples et vecteurs de test vérifiés par la CI.

- **Sortante uniquement**, HTTPS, aucun port ouvert, compatible avec un proxy HTTP.
- Chaque requête est **signée** par la clé de l'agent sur méthode, chemin, horodatage et hash du corps (inspiration : HTTP Message Signatures, RFC 9421). Aucun secret partagé ne transite.
- L'agent récupère ses ordres par **polling**. L'intervalle est **dicté par la console** dans chaque réponse, avec gestion de `429` / `Retry-After` et un jitter aléatoire. Le protocole est prêt pour le long polling (voir §9bis).

### Ordres (catalogue fermé)

Tous les ordres sont signés Ed25519 par la console et portent un id unique et une fenêtre de validité courte. L'agent garde une mémoire anti-rejeu persistée, qui survit au redémarrage.

| Ordre | Effet |
|---|---|
| `SCAN_NOW` | Relance un inventaire complet |
| `SET_CONFIG` | Racines de découverte, chemins déclarés, exclusions, intervalle |
| `UPGRADE_AGENT` | Mise à jour vers une version donnée (mode `host`). Le binaire est vérifié avec la **clé de release du projet** embarquée dans l'agent, pas celle de la console (décision 78). |
| `ROTATE_KEY` | Régénère la paire de clés de l'agent, qui prouve la nouvelle à la console (décision 79). |
| `ROTATE_CONSOLE_KEY` | Fait épingler à l'agent la nouvelle clé de la console, dans un ordre signé par l'ancienne (décision 79). |

**Aucune commande shell arbitraire, jamais.**

### Ce que l'agent collecte

- **Hôte** : distribution et version, noyau, paquets OS (base dpkg / rpm / apk).
- **Runtimes** : `php -v` et extensions, `composer --version`, `node -v`, npm/yarn/pnpm. Liste fixe de commandes, chemins détectés via `PATH` et les pools FPM.
- **PHP** : priorité à `vendor/composer/installed.json`, qui reflète ce qui est **réellement installé**. À défaut, `composer.lock`. Aussi `composer.json` (contrainte `php`), `symfony.lock`.
- **Node** : `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml` (et `node_modules/.package-lock.json` si présent).
- **Docker** : conteneurs en cours, images (nom, tag, digest), et inventaire des paquets **dans** les images.
- **Sortie** : un SBOM **CycloneDX** par AppInstance, plus les faits de l'hôte. Compressé et signé.

Comment chaque source est lue :
- **dpkg** : analyse directe de `/var/lib/dpkg/status`.
- **rpm** : commande fixe `rpm -qa --qf …`. La base est en BerkeleyDB ou SQLite selon la version.
- **apk** : `/lib/apk/db/installed`.
- **yarn.lock** : analyseur dédié.
- **Images Docker** : via l'API Docker (`bollard`), en exportant les couches et en relisant la base de paquets à l'intérieur. **C'est le point le plus coûteux de l'agent.** Il faut un cache par digest d'image pour ne pas réanalyser une image inchangée.

Aucun équivalent de Syft n'existe en Rust : les catalogueurs sont écrits dans le projet, avec des tests sur des fixtures réelles.

### Privilèges

- Utilisateur dédié non-root, accès en lecture seule aux répertoires des applications (groupe ou ACL).
- **Socket Docker = équivalent root.** L'accès doit être optionnel et documenté. Recommander un proxy de socket en lecture seule (type `docker-socket-proxy`, endpoints `GET` uniquement).

## 6bis. Applications conteneurisées (Docker, ECS)

### Principe : en conteneur, on inventorie l'image

Un conteneur est **immuable** : ce qui tourne est exactement ce qui est dans l'image. On inventorie donc **l'image, identifiée par son digest**, et on sait **quelles AppInstances l'exécutent**. Deux conséquences :
- 10 tâches ECS qui tournent sur la même image = **1 seule analyse**.
- Les versions des runtimes se lisent dans l'image : binaire `php` ou `node` présent, et variables `PHP_VERSION` / `NODE_VERSION` dans la configuration de l'image (posées par les images officielles).

**Nuance importante :** le code n'est pas toujours dans l'image. Il peut être monté en volume (bind mount), ou un `composer install` peut tourner au démarrage. L'agent complète donc l'analyse de l'image par une **lecture ciblée de fichiers dans le conteneur en cours**, via l'API Docker `GET /containers/{id}/archive?path=…`, qui est en lecture seule. Il lit ainsi `vendor/composer/installed.json`, les lockfiles, etc., **y compris sur les volumes montés**. On n'exporte pas tout le conteneur, seulement les fichiers d'inventaire.

**Identité d'une image** : les images viennent de sources variées (GHCR, registre privé, build local sur le serveur) :
- l'agent identifie toujours une image par son **Image ID** (digest de la configuration, `sha256:…`), qui existe aussi pour une image construite localement ;
- il ajoute les `RepoDigests` (digest registre) **quand ils existent**. Une image construite localement n'en a pas, ce qui est normal ;
- le cache d'analyse est indexé par Image ID ;
- une image buildée localement sur deux serveurs donne en général deux Image ID différents, donc deux analyses. C'est acceptable.
- La provenance (`registry` / `local-build`) est affichée dans la console. **L'image de base** est déduite du label OCI `org.opencontainers.image.base.name` s'il est présent, sinon de `/etc/os-release` dans l'image et de l'historique des couches.

Ce qu'on extrait d'une image :
- paquets OS (dpkg/apk/rpm dans les couches) ;
- dépendances applicatives (`vendor/composer/installed.json`, lockfiles Node) ;
- runtimes ;
- image de base. Sa fin de vie est aussi à suivre (ex. `node:18-alpine`).

### Les 4 façons de déployer l'agent

C'est **le même binaire Rust** dans tous les cas. Seuls le packaging et la variable `AGENT_MODE` changent.

| # | Déploiement | `AGENT_MODE` | Pour | Ce qu'il voit |
|---|---|---|---|---|
| 1 | **Binaire sur le serveur** (`curl … \| sh`, systemd) | `host` | Linux bare metal / VM, avec des applications **natives et/ou Docker** | OS de l'hôte + applications natives + conteneurs Docker (si activé) |
| 2 | **Conteneur dédié** (image officielle, un service dans le `docker-compose.yml`) | `container` | Docker / Compose sans rien installer sur l'hôte, ECS sur EC2 | Selon `AGENT_SCOPE` : son projet Compose (défaut), des conteneurs choisis par label, ou tout l'hôte |
| 3 | **Embarqué dans l'image de l'application** | `embedded` | Secours : pas d'accès à l'hôte ni au socket Docker | Le système de fichiers de son propre conteneur |
| 4 | **Collecteur cloud** | `ecs` | ECS Fargate (et plus tard d'autres plateformes managées) | Les tâches des clusters ciblés, via l'API AWS + ECR |

#### 1. Agent sur le serveur (`host`)

- Couvre l'OS (paquets, noyau), les runtimes, les applications natives (dossiers), **et les conteneurs Docker** de l'hôte.
- **Docker est optionnel et explicite.** Lire l'API Docker demande l'accès au socket, ce qui équivaut à root. L'option est proposée à l'installation (`AGENT_DOCKER=1`) et affichée dans la console. Sans elle, l'agent ignore Docker.
- Une fois Docker activé, il couvre les conteneurs comme le mode `container` en portée `host`, labels compris (voir plus bas).

#### 2. Agent en conteneur dédié (`container`)

**Image officielle, aucun script.**
- L'image `ghcr.io/dependencyverifier/agent` a pour `ENTRYPOINT` le binaire de l'agent.
- **Toute la configuration passe par des variables d'environnement** (et un secret pour le jeton). On ajoute un service au `docker-compose.yml`, `docker compose up -d`, et c'est tout : aucun fichier à créer, aucun script à lancer.
- L'image est minimale (distroless ou `scratch` + certificats CA), tourne en non-root, est signée cosign et multi-arch (amd64/arm64).

**Accès à Docker : via un proxy en lecture seule (recommandé).**
- L'agent ne monte **jamais** le socket Docker directement. Un second service, le proxy, est le seul à le monter, et n'autorise que des `GET`.
- **Décision MVP : proxy open source existant `tecnativa/docker-socket-proxy`**, configuré en `GET` uniquement (`CONTAINERS=1`, `IMAGES=1`, `INFO=1`, `VERSION=1`, `POST=0`).
- **C'est l'agent qui se limite lui-même** à sa portée (projet Compose, labels). Le proxy expose en lecture tous les conteneurs de l'hôte, donc l'isolation entre projets d'un même hôte est **logique**, pas technique. C'est acceptable car un hôte appartient à une seule équipe.
- Garde-fous côté agent :
  - le filtre de portée est appliqué **avant** toute lecture de fichier ou analyse d'image ;
  - un conteneur hors portée n'est **jamais** inspecté en profondeur ni remonté ;
  - ce comportement est couvert par des tests.
- Garde-fou côté console : elle rejette et trace toute remontée d'un agent `compose` / `labeled` qui concerne un conteneur dont le label `com.docker.compose.project` diffère de celui déclaré par l'agent à l'appairage.
- *Roadmap :* une image de proxy maison (`ghcr.io/dependencyverifier/docker-proxy`) qui filtre par projet Compose et par label, pour une isolation technique.
- Variante « un seul service » : l'agent monte directement le socket. C'est plus simple, mais l'agent devient équivalent à root sur l'hôte. Documentée, mais **déconseillée**.

**Portée de la surveillance : `AGENT_SCOPE`**

| `AGENT_SCOPE` | Conteneurs surveillés | Usage |
|---|---|---|
| `compose` (**défaut**) | **Tous** les conteneurs de son projet Compose (détecté automatiquement via le label `com.docker.compose.project`), sauf ceux marqués `dev.depverify.monitor=false` | Cas standard : « je surveille mon projet » |
| `labeled` | **Seulement** les conteneurs de son projet Compose marqués `dev.depverify.monitor=true` | « Je ne veux surveiller que `app` et `worker`, pas `redis` ni `mailpit` » |
| `host` | **Tous** les conteneurs de l'hôte, sauf `dev.depverify.monitor=false`. Avec montage `/host:ro`, aussi l'OS de l'hôte | Un seul agent pour tout un hôte Docker, ECS sur EC2 (service `DAEMON`) |

**Labels Docker reconnus**, posés sur les services de l'application dans le `docker-compose.yml`. Ils sont tous optionnels :

| Label | Effet | Défaut |
|---|---|---|
| `dev.depverify.monitor` | `true` / `false` : inclure ou exclure ce conteneur | inclus (sauf en portée `labeled`) |
| `dev.depverify.name` | Nom affiché de l'application dans la console | nom du service Compose |
| `dev.depverify.environment` | **UUID** de l'environnement auquel rattacher ce service | environnement par défaut du jeton d'enrôlement |
| `dev.depverify.paths` | Chemins dans le conteneur où chercher `composer.lock`, `installed.json`, lockfiles Node… (séparés par des virgules) | détection automatique (`WORKDIR`, `/app`, `/var/www/html`, `/srv/app`…) |

*Préfixe en notation DNS inversée, selon la convention Docker. C'est une constante du produit, identique sur toutes les instances : elle ne dépend pas du domaine de chaque console (voir §3, « Domaine »).*

**Sécurité des labels :** un label n'est qu'une **proposition**. La console vérifie que l'environnement visé appartient bien à l'équipe de l'agent, sinon elle refuse et le trace dans l'audit. Un rattachement à un environnement autre que celui par défaut du jeton peut exiger une validation de l'admin (réglage d'équipe).

**Exemple complet**, généré par la console avec le jeton et l'image épinglée par digest :

```yaml
services:
  app:
    image: registry.example.com/mon-projet/app:1.4.2
    labels:
      dev.depverify.name: "API publique"
      dev.depverify.paths: "/var/www/api"
  worker:
    image: registry.example.com/mon-projet/app:1.4.2
    labels:
      dev.depverify.name: "Worker Messenger"
  redis:
    image: redis:7.4
    labels:
      dev.depverify.monitor: "false"      # exclu de la surveillance
  mailpit:
    image: axllent/mailpit
    labels:
      dev.depverify.monitor: "false"

  monitoring-agent:
    image: ghcr.io/dependencyverifier/agent@sha256:<digest>      # épinglé par digest, signé cosign
    restart: unless-stopped
    environment:
      AGENT_MODE: container
      AGENT_SCOPE: compose                              # défaut, peut être omis
      AGENT_CONSOLE_URL: https://console.example.com
      AGENT_CONSOLE_PUBKEY: "<clé publique de la console>"
      AGENT_TOKEN_FILE: /run/secrets/agent_token        # lu uniquement au 1er démarrage
      DOCKER_HOST: tcp://monitoring-docker-proxy:2375
    secrets: [agent_token]
    volumes:
      - monitoring-agent-data:/var/lib/agent           # clé privée + anti-rejeu : DOIT persister
    networks: [monitoring-internal, default]           # default = sortie HTTPS vers la console
    read_only: true
    cap_drop: [ALL]
    security_opt: ["no-new-privileges:true"]

  monitoring-docker-proxy:
    image: tecnativa/docker-socket-proxy:<version épinglée>
    environment:
      CONTAINERS: 1   # inspect + archive (lecture ciblée de fichiers)
      IMAGES: 1       # inspect + export des couches
      INFO: 1
      VERSION: 1
      POST: 0         # aucune écriture, aucun exec, aucun start/stop
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    networks: [monitoring-internal]                     # réseau interne, jamais exposé
    read_only: true

networks:
  monitoring-internal:
    internal: true

volumes:
  monitoring-agent-data:

secrets:
  agent_token:
    file: ./.agent_token    # inutile après l'appairage (jeton à usage unique)
```

**Fonctionnement :**
- Pour chaque conteneur retenu, l'agent récupère le **digest de l'image**, l'analyse **une fois** (cache par digest), puis lit en ciblé les fichiers d'inventaire dans le conteneur en cours (API `archive`, voir la nuance plus haut). Les labels `dev.depverify.paths` orientent cette lecture.
- Il remonte aussi la version du **moteur Docker / containerd / runc**.
- 1 service Compose retenu = 1 AppInstance. Un service répliqué (`deploy.replicas: 3`) reste **une seule** AppInstance, avec ses N conteneurs.
- Plusieurs agents `container` sur le même hôte sont regroupés par la console sous un même Host, grâce à l'ID du moteur Docker.

**Limites :**
- En portée `compose` ou `labeled`, **l'OS de l'hôte n'est pas couvert**, seulement le moteur Docker et les conteneurs. Pour l'hôte, il faut un agent `host`, ou un agent `container` en portée `host` avec `/host:ro`.
- Le volume `monitoring-agent-data` doit survivre aux `docker compose down` (pas de `-v`), sinon l'agent se réenrôle et doit être revalidé.
- Chaque projet Compose = un agent à valider et à compter dans le quota `maxAgents`.

**ECS sur EC2 :**
- même image, en `AGENT_SCOPE=host` ;
- déployée comme service ECS en stratégie `DAEMON` : un agent par instance ;
- volume d'état sur l'instance (`/var/lib/depverify-agent`) ;
- en autoscaling, utiliser un **jeton d'enrôlement réutilisable** (voir §6).

#### 3. Agent embarqué dans l'image de l'application (`embedded`, secours)

Possible quand on ne peut ni installer sur l'hôte, ni accéder au socket Docker (hébergeur restrictif, PaaS…) :

```dockerfile
COPY --from=ghcr.io/dependencyverifier/agent@sha256:<digest> /agent /usr/local/bin/depverify-agent
```

L'agent est lancé à côté de l'application (init type `tini` / `s6-overlay`, ou wrapper d'entrypoint) avec `AGENT_MODE=embedded`. Il inventorie **son propre système de fichiers**, ce qui couvre exactement ce qui tourne, volumes compris.

Pourquoi ce n'est pas le mode recommandé :
- il faut **modifier et reconstruire chaque image** ;
- il faut gérer deux processus dans un conteneur prévu pour un seul ;
- **chaque réplique = un agent** : avec 3 répliques, ce sont 3 appairages, et l'identité est perdue à chaque recréation si elle n'est pas persistée en volume ;
- les mises à jour de l'agent suivent celles de l'application ;
- l'agent tourne avec les droits de l'application ;
- le moteur Docker et l'hôte ne sont pas couverts.

#### Comparatif

| Critère | 1. `host` | 2. `container` | 3. `embedded` |
|---|---|---|---|
| Installation sur l'hôte | Oui | **Non** (un service Compose) | Non |
| Modifier les images applicatives | Non | **Non** | Oui, toutes |
| Applications natives (hors Docker) | Oui | Non | Non |
| Conteneurs | Oui (si Docker activé) | Oui, avec choix par portée et labels | Le sien uniquement |
| OS de l'hôte | Oui | Seulement en portée `host` + `/host:ro` | Non |
| Moteur Docker | Oui (si Docker activé) | Oui | Non |
| Nombre d'agents | 1 par hôte | 1 par projet Compose (ou 1 par hôte en portée `host`) | 1 par conteneur ou réplique |
| **Recommandé pour** | Serveurs que l'on administre | **Hôtes Docker partagés, projets autonomes** | Secours uniquement |

#### Mode `ecs` (collecteur Fargate, sans hôte, hors MVP)

Sur Fargate, il n'y a ni hôte accessible, ni socket Docker, ni service « daemon ». Le collecteur fonctionne donc sans entrer dans les conteneurs :

1. **Ce qui tourne** : il interroge l'API ECS (`ListClusters`, `ListServices`, `DescribeServices`, `ListTasks`, `DescribeTasks`, `DescribeTaskDefinition`) pour obtenir, par service et par conteneur, le **digest d'image réellement exécuté**.
2. **Ce que contient l'image** : il télécharge l'image depuis ECR (`ecr:GetAuthorizationToken`, `BatchGetImage`, `GetDownloadUrlForLayer`), l'analyse **localement** avec les mêmes catalogueurs que les autres modes, puis la jette. Le cache par digest évite toute réanalyse.
3. Il envoie à la console un SBOM par image et la correspondance service → digest.

Sécurité :
- **Aucune clé AWS stockée** : le collecteur utilise le **rôle IAM de sa tâche ECS** (ou un rôle assumé pour un autre compte). La console ne détient **jamais** d'identifiants AWS.
- Politique IAM en **lecture seule stricte** (`Describe*` / `List*` ECS, lecture ECR), limitée aux clusters et dépôts concernés. Un exemple de politique est fourni dans la doc.
- Même modèle que les autres agents : connexion sortante seule, appairage validé par un humain, ordres signés.

Mapping dans la console :
- 1 CloudScope = compte AWS + région + clusters ciblés ;
- 1 **service ECS** (+ nom de conteneur) = 1 AppInstance, rattachée à un Environment ;
- découverte automatique des services, puis rattachement validé par l'admin, comme pour les dossiers sur un hôte.

#### Alternatives écartées ou de secours

- **Sidecar dans chaque tâche Fargate** (`pidMode: task` + `SYS_PTRACE` pour lire `/proc/<pid>/root` du conteneur applicatif). C'est possible, mais intrusif : il faut modifier chaque task definition, cela coûte des ressources par tâche et demande des capacités sensibles. Il ne serait utile que pour les images non accessibles depuis un registre.
- **Agent embarqué dans l'image applicative** : voir le mode `embedded` plus haut, réservé aux cas de secours.
- **Source CI** (roadmap) : le pipeline envoie le SBOM de l'image au moment du build. Avec le mode `ecs`, qui sait quel digest tourne, on peut alors se passer du téléchargement des images.

### Autres registres

Le même principe « liste de ce qui tourne + analyse de l'image par digest » s'étendra à d'autres plateformes (Kubernetes, Cloud Run, Azure Container Apps…) et registres (Docker Hub, GHCR, GitLab, Harbor). L'abstraction `CloudScope` est prévue pour ça.

## 7. Sécurité de la console

- **Secrets jamais relisibles** : jetons d'enrôlement et jetons d'API stockés hachés, affichés une seule fois.
- **Secrets au repos** (secrets HMAC des webhooks, identifiants SMTP, secrets TOTP…) chiffrés en AES-256-GCM, clé maîtresse hors base (variable d'environnement ou fichier).
- La **clé privée de signature** de la console ne quitte jamais le serveur. Sa rotation suit la procédure de la décision 79.
- **Cloisonnement** : chaque requête, chaque vue et chaque ordre vérifie que la ressource appartient au périmètre de l'utilisateur. Le contrôle est **centralisé** (voters Symfony) et pas ajouté action par action.
- **Journal d'audit** :
  - posé globalement, sur toutes les routes, UI comme API agents ;
  - qui, quoi, sur quoi, résultat, IP ;
  - refus tracés et distingués des erreurs serveur ;
  - **jamais le corps des requêtes** ;
  - en **ajout seul** : schéma `audit` dont le rôle runtime n'a que `INSERT` et `SELECT`, triggers PostgreSQL qui refusent `UPDATE`, `DELETE` et `TRUNCATE`, partitions mensuelles ;
  - un refus est écrit **une seule fois**, qu'il vienne du firewall, d'un voter, d'une commande ou d'une requête ; un objet hors du périmètre de l'acteur répond 404, un objet visible sans la permission 403 ;
  - purge uniquement par une tâche de rétention configurée par l'exploitant.
- **Auth** :
  - **connexion principale : email + mot de passe** (Argon2id), **toujours suivie d'un second facteur** :
    - **TOTP** si l'utilisateur l'a configuré ;
    - sinon **code à usage unique envoyé par email** : 6 chiffres ou plus, stocké haché, expiration ~10 min, nombre d'essais limité, invalidé dès usage ;
  - **passkey (WebAuthn) proposée, jamais obligatoire** :
    - bouton « Se connecter avec une passkey » sur l'écran de connexion, en alternative au couple mot de passe + second facteur ;
    - compatible clés matérielles (YubiKey…), trousseau de la plateforme (iCloud, Google, Windows Hello) et gestionnaires de mots de passe (Bitwarden, 1Password…) ;
    - credential découvrable (`residentKey: preferred`) et `userVerification: required`, pour que la passkey vaille à elle seule une authentification multifacteur ;
    - plusieurs passkeys par compte, nommées, révocables individuellement depuis le profil ;
    - vérification de l'origine (`rpId` = domaine de l'instance) et du compteur de signatures ;
  - second facteur **à chaque connexion, pour tout le monde** (décision du 09/11/2026). Tout second facteur est accepté, **y compris le code par email**, admins compris ; TOTP et passkey restent proposés. « Faire confiance à cet appareil » le saute pendant 30 jours ;
  - enregistrement, révocation et usage des passkeys et du TOTP **tracés dans l'audit** ; échecs répétés limités (rate limiting par compte et par IP) ;
  - pas d'inscription libre : création de compte **sur invitation uniquement**. Pas de connexion via un fournisseur tiers (GitHub…) au MVP ;
  - sessions courtes, cookies `HttpOnly` / `Secure` / `SameSite=Strict` ;
  - *(post-MVP, avec l'API publique)* jetons d'API avec droits limités et expiration, transmis via l'en-tête `Authorization`, jamais dans l'URL.
- **Souveraineté** : aucune télémétrie. Les seuls flux sortants de la console sont les **téléchargements** des bases publiques, qui peuvent être désactivés ou, à partir de la V1, passer par un miroir (mode air-gap). L'interface ne charge **aucune ressource externe** (polices, scripts, CDN) : tout est servi par l'instance.

## 7bis. Gestion des droits

### Principes

- **3 niveaux** : instance, équipe, projet.
- **Niveau instance = rôles Symfony natifs.** Le statut de super admin a une source unique, le `User` du domaine (`isSuperAdmin`), traduit en `ROLE_SUPER_ADMIN` par la sécurité, avec une `role_hierarchy` (`ROLE_SUPER_ADMIN: [ROLE_USER]`) et utilisable via `#[IsGranted('ROLE_SUPER_ADMIN')]` et `access_control`. Les rôles Symfony sont **globaux**, ils ne peuvent pas porter « admin de l'équipe 1 mais invité dans l'équipe 3 ». Les rôles d'équipe et de projet restent donc dans les memberships, et sont évalués par des voters.
- **Rôles d'équipe et de projet fixes** définis dans le code (enums PHP). Chaque rôle est un **lot de permissions par défaut**, tiré d'un catalogue de permissions.
- **Permissions additionnelles** : on peut accorder individuellement une permission en plus du rôle (`extraPermissions` sur la membership), par exemple `project.create` à un `TEAM_MEMBER` ou `finding.accept_risk` à un `PROJECT_MEMBER`. Les ajouts sont uniquement additifs : pour retirer un droit, on change de rôle.
- Les voters Symfony ne testent **que des permissions**, jamais des rôles. On pourra ainsi ajouter des rôles personnalisés plus tard sans toucher aux voters.
- Un utilisateur peut appartenir à **plusieurs équipes**, avec un rôle différent dans chacune, **sans forcément gérer ni voir toute l'équipe**.
- **`TEAM_GUEST`** : l'utilisateur fait partie de l'équipe (elle apparaît dans son sélecteur d'équipe) mais **ne voit que les projets où il a une ProjectMembership**.
- **Permission effective** sur un projet = permissions du rôle d'équipe + permissions additionnelles d'équipe + permissions du rôle projet + permissions additionnelles du projet. Le super admin a **toutes** les permissions, sur toutes les équipes et tous les projets.
- **Le super admin a les pleins pouvoirs sur toute l'instance**, sans avoir besoin d'être membre d'une équipe. Il crée les équipes, fixe leurs quotas et nomme le ou les premiers `TEAM_ADMIN`. Ensuite, l'équipe est **autonome** : membres, projets, appairage des agents. Le super admin n'est **requis** pour rien au quotidien, mais il **peut tout faire** : valider ou révoquer un agent, agir sur n'importe quel projet, etc.
- **Protection de `ROLE_SUPER_ADMIN`** :
  - seul un super admin peut l'attribuer ;
  - seul un **autre** super admin peut le retirer : un super admin ne peut pas se le retirer lui-même, ni être rétrogradé par un admin d'équipe ;
  - impossible de retirer le dernier super admin actif ;
  - le premier super admin est créé en ligne de commande à l'installation (`bin/console app:user:create-super-admin`) ;
  - 2FA obligatoire ;
  - chaque attribution ou retrait est tracé dans l'audit.
- Accès d'un utilisateur limité à certains projets : il voit les failles système (OS, runtimes) des hôtes qui portent ses projets, **en lecture seule**. La gestion des hôtes et des agents reste au niveau de l'équipe.

### Rôles

| Niveau | Rôle | Portée |
|---|---|---|
| Instance | `ROLE_SUPER_ADMIN` (rôle Symfony) | **Pleins pouvoirs sur tout** : comptes, équipes, quotas (et quotas par défaut), paramètres de l'instance, sources de données, audit global, tous les agents, tous les projets |
| Équipe | `TEAM_ADMIN` | Gestion de l'équipe (membres, hôtes, agents, canaux) + admin de **tous** ses projets |
| Équipe | `TEAM_MEMBER` | Membre de **tous** les projets de l'équipe, sans gestion de l'équipe |
| Équipe | `TEAM_VIEWER` | Lecture seule sur **tous** les projets de l'équipe |
| Équipe | `TEAM_GUEST` | Présence dans l'équipe, **aucun projet par défaut** : uniquement ceux où il a un rôle projet |
| Projet | `PROJECT_ADMIN` | Gestion complète d'**un** projet |
| Projet | `PROJECT_MEMBER` | Travail courant sur **un** projet |
| Projet | `PROJECT_VIEWER` | Lecture seule sur **un** projet |

### Catalogue de permissions (validé)

Légende :
- SA = `ROLE_SUPER_ADMIN` ; TA / TM / TV / TG = rôles d'équipe ; PA / PM / PV = rôles projet.
- ✓ = inclus par défaut dans le rôle.
- ○ = **non inclus par défaut, mais peut être accordé individuellement** à ce rôle.
- vide = impossible pour ce rôle. Il faut changer de rôle.

| Permission | Portée | SA | TA | TM | TV | TG | PA | PM | PV |
|---|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|
| `instance.settings` (SMTP, sources, rétention) | instance | ✓ | | | | | | | |
| `instance.users.manage` (comptes, reset 2FA, désactivation) | instance | ✓ | | | | | | | |
| `instance.audit.view` | instance | ✓ | | | | | | | |
| `team.create` / `team.delete` | instance | ✓ | | | | | | | |
| `team.quotas.manage` / `instance.default_quotas.manage` | instance | ✓ | | | | | | | |
| `instance.super_admin.manage` (attribuer ou retirer `ROLE_SUPER_ADMIN` à un **autre** utilisateur) | instance | ✓ | | | | | | | |
| `instance.agents.view` (vue globale : statut, version, dernière remontée, équipe) | instance | ✓ | | | | | | | |
| `team.edit` (nom, paramètres, hors quotas) | équipe | ✓ | ✓ | | | | | | |
| `team.members.manage` (inviter, rôles, permissions, retirer) | équipe | ✓ | ✓ | | | | | | |
| `team.audit.view` | équipe | ✓ | ✓ | ○ | ○ | | | | |
| `team.channels.manage` (canaux partagés de l'équipe) | équipe | ✓ | ✓ | ○ | | | | | |
| `host.enroll` (créer un jeton d'enrôlement) | équipe | ✓ | ✓ | ○ | | | | | |
| `host.approve` (valider l'appairage) | équipe | ✓ | ✓ | ○ | | | | | |
| `host.revoke` | équipe | ✓ | ✓ | ○ | | | | | |
| `host.delete` | équipe | ✓ | ✓ | ○ | | | | | |
| `host.order` (`SCAN_NOW`, `SET_CONFIG`) | équipe | ✓ | ✓ | ○ | | | | | |
| `host.edit` (nom d'affichage et adresses IP d'un hôte, liens de documentation d'une application non rattachée) | équipe | ✓ | ✓ | ○ | | | | | |
| `host.view` (hôtes portant un projet accessible) | projet | ✓ | ✓ | ✓ | ✓ | – | ✓ | ✓ | ✓ |
| `project.create` | équipe | ✓ | ✓ | ○ | | ○ | | | |
| `project.edit` | projet | ✓ | ✓ | ○ | | – | ✓ | ○ | |
| `project.delete` | projet | ✓ | ✓ | ○ | | – | ○ | | |
| `project.members.manage` | projet | ✓ | ✓ | ○ | | – | ✓ | ○ | |
| `project.environments.manage` | projet | ✓ | ✓ | ✓ | | – | ✓ | ○ | |
| `project.apps.assign` (rattacher une app découverte) | projet | ✓ | ✓ | ✓ | | – | ✓ | ○ | |
| `project.scan_now` | projet | ✓ | ✓ | ✓ | | – | ✓ | ✓ | ○ |
| `project.notifications.manage` (règles + rattachement des comptes « notification seule ») | projet | ✓ | ✓ | ✓ | | – | ✓ | ○ | |
| `project.notifications.subscribe` (ses propres préférences) | projet | ✓ | ✓ | ✓ | ✓ | – | ✓ | ✓ | ✓ |
| `finding.view` | projet | ✓ | ✓ | ✓ | ✓ | – | ✓ | ✓ | ✓ |
| `finding.accept_risk` | projet | ✓ | ✓ | ○ | | – | ✓ | ○ | |
| `finding.export` (SBOM, rapport) | projet | ✓ | ✓ | ✓ | ✓ | – | ✓ | ✓ | ✓ |
| `apitoken.manage` (ses propres jetons, plafonnés à ses droits, *post-MVP*) | utilisateur | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

« – » pour `TEAM_GUEST` : il n'a aucun droit projet via son rôle d'équipe. Ses droits projet viennent uniquement de ses rôles projet.

La colonne SA est entièrement cochée : le super admin a **toutes** les permissions, même sans membership. Les permissions `host.*` s'appliquent aussi aux agents en mode `ecs` (CloudScope).

**Comptes « notification seule »** : ils ont une membership (en pratique `PROJECT_VIEWER` ou `TEAM_VIEWER`) qui délimite **ce qu'ils peuvent recevoir**. Ils n'ont aucune autre permission, puisqu'ils ne peuvent pas se connecter. Le contenu d'une notification ou d'un digest est filtré comme pour n'importe quel utilisateur.

*La matrice sert aussi de base aux tests : un test par case, plus un test par permission additionnelle.*

### Exemple : l'utilisateur 3

Les équipes 1 et 3 ont chacune 5 projets.

| Membership | Rôle | Effet |
|---|---|---|
| Équipe 1 | `TEAM_GUEST` | L'équipe 1 apparaît dans son sélecteur, sans aucun projet par défaut |
| Équipe 1 / Projet 2 | `PROJECT_MEMBER` + `finding.accept_risk` | Travaille sur le projet 2 et peut accepter un risque |
| Équipe 1 / Projet 4 | `PROJECT_VIEWER` | Lecture seule |
| Équipe 3 | `TEAM_GUEST` + `project.create` | Peut créer un projet dans l'équipe 3. Il en devient automatiquement `PROJECT_ADMIN`. |
| Équipe 3 / Projet 1 | `PROJECT_ADMIN` | Gestion complète du projet 1 |
| Équipe 3 / Projet 5 | `PROJECT_MEMBER` | Travail courant |

Il ne voit **jamais** les projets 1, 3 et 5 de l'équipe 1, ni les projets 2, 3 et 4 de l'équipe 3. Il ne les voit ni dans les listes, ni dans les recherches, ni dans les digests, ni via l'API. Il ne voit pas non plus la gestion des équipes, ni les hôtes qui ne portent aucun de ses projets.

### Règles de garde

- Une équipe garde **au moins un `TEAM_ADMIN` actif** dès sa création (premier admin admis directement, décision 12), et l'instance au moins un `ROLE_SUPER_ADMIN` actif. Le super admin peut désactiver le dernier admin d'une équipe, qui n'est alors plus gérée que par lui.
- Ordre des rôles (décision du 09/11/2026) : `TEAM_ADMIN` > `TEAM_MEMBER` > `TEAM_VIEWER` > `TEAM_GUEST`, `PROJECT_ADMIN` > `PROJECT_MEMBER` > `PROJECT_VIEWER`. Un `TEAM_ADMIN` couvre tous les rôles projet de son équipe ; un `TEAM_MEMBER` a, dans les projets de son équipe, au moins le rang d'un `PROJECT_MEMBER` (décision du 11/11/2026) ; un `PROJECT_ADMIN` peut nommer un autre `PROJECT_ADMIN` mais ne touche jamais aux rôles d'équipe, et ne retire jamais d'un projet un membre de l'équipe (`TEAM_MEMBER` ou plus). Personne ne modifie ni ne retire un membre de rang supérieur au sien.
- Un `TEAM_GUEST` qui n'a plus aucun projet **reste membre** (et compte dans `maxMembers`) jusqu'à son retrait explicite.
- `ROLE_SUPER_ADMIN` ne peut être retiré que par un **autre** super admin (voir Principes).
- Un utilisateur ne peut attribuer qu'un rôle **inférieur ou égal** au sien, et ne peut accorder **que des permissions qu'il détient lui-même** sur ce périmètre. Pas d'escalade de privilèges.
- Une permission additionnelle ne peut être accordée que si elle est marquée ○ pour le rôle de la membership. Les permissions d'instance ne sont jamais accordables.
- Les permissions d'**équipe** (`team.*`, `host.*`, `project.create`) s'accordent sur la TeamMembership. Les permissions de **projet** s'accordent sur la ProjectMembership.
- Créer un projet donne automatiquement le rôle `PROJECT_ADMIN` sur ce projet au créateur, sauf s'il a déjà un rôle d'équipe qui le couvre.
- Chaque ajout ou retrait de rôle ou de permission est tracé (PermissionGrant + audit). Les notifications et les digests sont filtrés selon les droits **au moment de l'envoi**.
- Un **jeton d'API** porte un sous-ensemble des permissions de son créateur et perd ses droits si l'utilisateur les perd.
- Les accès du super admin aux données d'une équipe sont **tracés** dans l'audit comme les autres.

### Implémentation Symfony

- `ROLE_SUPER_ADMIN` est géré par la sécurité Symfony native (`User.roles`, `role_hierarchy`, `access_control` sur `/admin`). Le `PermissionResolver` court-circuite tout pour ce rôle : toutes les permissions sont accordées. L'action reste tracée dans l'audit.
- La règle « seul un autre super admin peut retirer le rôle » est appliquée dans le service métier de gestion des utilisateurs, et pas seulement dans l'UI.
- Un `UserChecker` refuse la connexion d'un compte désactivé ou sans la permission d'instance `account.login`, avec un message générique.
- Un `PermissionResolver` calcule une fois par requête les permissions effectives de l'utilisateur **par équipe et par projet**, à partir de `ROLE_SUPER_ADMIN`, des rôles et des `extraPermissions` des TeamMembership et ProjectMembership.
- Une table de correspondance unique dans le code définit, pour chaque rôle, les permissions par défaut (✓) et les permissions accordables (○). Elle sert à la fois au resolver, à l'UI d'attribution et aux tests.
- Les voters `TeamVoter`, `ProjectVoter`, `HostVoter` et `FindingVoter` délèguent au resolver.
- Les requêtes Doctrine de listing sont **filtrées par périmètre**, via un filtre ou des repositories dédiés, pour qu'une liste ne fuite jamais d'objet hors périmètre.
- Les **quotas** d'équipe sont vérifiés dans les services métier (création de projet, d'environnement, de jeton d'enrôlement, validation d'agent, invitation) et pas seulement dans l'UI. Le dépassement est **bloquant**, y compris pour un appel via l'API, **et pour le super admin** : c'est lui qui les ajuste, avant d'agir.

## 8. Moteur d'analyse

### Sources (synchronisation locale)

| Source | Usage |
|---|---|
| **OSV.dev** (exports zip par écosystème) | Vulnérabilités Packagist, npm, Debian, Ubuntu, Alpine, AlmaLinux/Rocky, RHEL et ses canaux (décisions 73, 80), SUSE et openSUSE (décision 81). |
| GitHub Advisory DB / FriendsOfPHP security-advisories | Complément PHP. La plupart des entrées sont déjà dans OSV. |
| **endoflife.date** (API) | Fins de vie des runtimes, frameworks et distributions (PHP, Node, Symfony, Laravel, Drupal, Debian, MySQL…). |
| **CISA KEV** | CVE activement exploitées, pour prioriser. |
| **EPSS** (FIRST) | Probabilité d'exploitation, pour prioriser. |
| Packagist / registre npm | Dernières versions disponibles, pour détecter les dépendances obsolètes. |

### Matching

- **Nouveau snapshot** : diff avec le précédent, puis matching de chaque composant contre les advisories indexées par `(écosystème, nom)`.
- **Nouvelle advisory** : index inverse, puis recalcul des seules AppInstances concernées.
- **Comparaison de versions propre à chaque écosystème** : Composer (`composer/semver`), npm (semver), Debian (`dpkg --compare-versions`), RPM, Alpine. C'est un point de complexité.
- **Paquets OS** : il faut utiliser les advisories **de la distribution** (backports), pas les plages upstream. Sinon, on obtient des faux positifs en masse.
- **Fin de vie** : alertes à J-180, J-90 et J-30 avant la fin du support sécurité, puis une alerte au dépassement. Exemple concret : **PHP 8.2 perd son support sécurité le 31/12/2026**.
- **Obsolescence** : retard de version mineure ou majeure sur les dépendances directes.
- **Dashboard** : vue par équipe, projet, environnement et hôte. Une suggestion du type « PHP 8.2 → 8.5 » s'appuie sur endoflife.date (dernier cycle supporté).

### Notifications

- **Événements** :
  - nouvelle vulnérabilité ;
  - vulnérabilité corrigée ;
  - fin de vie approchante ou dépassée ;
  - dépendance obsolète ;
  - **agent muet** depuis X h ;
  - agent en attente de validation ;
  - expiration d'une acceptation de risque.
- **Règles par projet**, et éventuellement par environnement :
  - événements activés ;
  - seuil (CVSS ≥ N, KEV uniquement, EPSS ≥ N) ;
  - mode **immédiat** ou **digest** quotidien / hebdomadaire ;
  - canaux.

  Un projet peut n'avoir **aucune** notification.
- **Canaux** : email, webhook custom (payload JSON documenté, signé HMAC-SHA256, avec retries), Slack/Teams/Discord via un composant de type Notifier.
- **Acceptation de risque** : justification et date d'expiration obligatoires, tracées dans l'audit. Elle neutralise les notifications sur ce Finding jusqu'à expiration.

## 9. Stack (décidée)

**Console : Symfony** (dernière stable 8.x) + **PHP 8.5** + **PostgreSQL**.

- **PostgreSQL retenu plutôt que MariaDB**, malgré l'homogénéité avec les autres projets de l'auteur. Les raisons :
  - index uniques partiels pour les règles « unique si actif » (finding ouvert, jetons et agents actifs) ;
  - DDL transactionnel dans les migrations ;
  - partitionnement compatible avec les clés étrangères (`snapshot`, `audit_log`) ;
  - JSONB indexable pour les SBOM et les faits ;
  - `LISTEN/NOTIFY` pour le transport Messenger.

  En dev, Adminer et `make db-dump` / `db-import` remplacent phpMyAdmin et les scripts MariaDB.

- C'est une stack maîtrisée, ce qui permet la vélocité et la maintenance.
- Base du projet : template **`dunglas/symfony-docker`** (FrankenPHP + Caddy, Dockerfile multi-stage dev/prod).
- **Architecture DDD** : un bounded context par namespace racine, chacun découpé en couches `src/<Contexte>/{Domain,Application,Infrastructure,UI}` :
  - `Shared` (noyau technique, bus, healthcheck, coquille web) ;
  - `Identity` (comptes, authentification, invitations) ;
  - `Organization` (équipes, quotas, projets, environnements, droits) ;
  - `Fleet` (hôtes, agents, enrôlement, ordres, API agent) ;
  - `Inventory` (sources, snapshots, composants, AppInstances, images) ;
  - `Vulnerability` (advisories, fins de vie, synchronisation des sources) ;
  - `Exposure` (matching, findings, acceptations de risque) ;
  - `Notification` ;
  - `Audit`.

  Le Domain ne dépend que de lui-même et de `Shared\Domain`. L'Application ne dépend que du Domain et des ports. Un contexte métier n'importe jamais un autre contexte métier. Ces règles sont vérifiées par un test d'architecture.
- **CQRS** sur 3 bus Messenger : `command.bus` (transactionnel), `query.bus` et `event.bus`, comme dans les autres projets de l'auteur.
- **Qualité** : PHPStan niveau max, php-cs-fixer, Rector, PHPUnit, Infection (100 % de MSI sur Domain et Application). Tout passe par un Makefile (`make qa`).
- **Front-end en TypeScript strict uniquement** : aucun fichier `.js` dans `assets/`, vérifié par `make typecheck`. **Pas de Mercure**, le projet n'a pas besoin de hub temps réel. Les **migrations Doctrine sont rangées par année** (`migrations/<AAAA>/`).
- **Healthcheck** : `GET /_healthcheck`. La page vient de Romain-MILLAN-Healthcheck, adaptée pour ne charger aucune ressource externe. Elle exécute des sondes (base de données…), renvoie 503 en JSON si une dépendance tombe et sert de healthcheck au conteneur.
- **Signature** : le footer affiche le tag Romain MILLAN, intégré en submodule git (`console/assets/romain-millan-tag`).
- **Domaine local de développement** : `https://console.depverify.localhost`.
- **Messenger** (transport Doctrine, sans Redis requis) et **Scheduler** pour les synchros et le matching. **Notifier** pour les canaux. **Security** (voters) pour le cloisonnement.
- `composer/semver` est natif pour Composer. Il existe des implémentations PHP de semver npm. La comparaison dpkg/rpm est à implémenter ou à porter.
- Front : **Twig + Symfony UX (Turbo, Stimulus, Twig Components, Live Components)** pour un seul déployable simple à auto-héberger.
  - Assets compilés par **Vite** via **Symfony Reprise** (successeur de Webpack Encore, encore expérimental : à surveiller). Node n'est utilisé qu'au build, via un conteneur `node` (`docker compose exec node yarn …`).
  - **Tailwind CSS v4** + composants du **Symfony UX Toolkit (kit `shadcn`)**, copiés dans `templates/components/` et donc maîtrisés par le projet.
  - Charte détaillée dans `docs/design.md`.
  - API Platform peut s'ajouter plus tard pour l'API publique.
- Distribution : image Docker **FrankenPHP** + `docker-compose.yml` (console, worker, PostgreSQL).

**Agent : Rust** (binaire statique musl, sécurité mémoire, `rustls`, `ed25519-dalek`).

Contrepartie : pas de Syft, donc des catalogueurs maison (voir §6). Contrat entre l'agent et la console : **SBOM CycloneDX** + un schéma JSON versionné pour les faits de l'hôte et les ordres.

## 9bis. Dimensionnement : 200 agents aujourd'hui, 2 000 demain

**MVP (≤ 200 agents)** : une console, un worker Messenger (transport Doctrine), PostgreSQL. Polling des agents toutes les 1 à 5 min.

Ce qu'il faut faire **dès le MVP** pour monter à 2 000 agents sans refonte :

- **Protocole agent prêt pour le long polling.** La console dicte l'intervalle de polling dans chaque réponse (`next_poll_in`) et peut répondre `429` + `Retry-After`. L'agent respecte toujours ces consignes. Passer au long polling ne demandera alors qu'un changement côté console.
- **Jitter côté agent** : décalage aléatoire sur l'inventaire (6 h ± x min) et sur le polling, pour éviter que 2 000 agents frappent la console à la même seconde, par exemple après une coupure.
- **Envois idempotents et dédupliqués** : chaque snapshot porte le hash de son contenu. Si rien n'a changé, l'agent n'envoie que le hash, et la console répond « déjà connu », sans re-parser ni re-matcher.
- **Traitement asynchrone** : l'API agent ne fait que valider la signature, stocker le snapshot brut et publier un message. Le parsing, le diff, le matching et les notifications se font dans des workers. L'API reste rapide quelle que soit la charge.
- **Console sans état** : sessions et cache en base ou dans un cache partagé, aucun fichier local. On peut ainsi lancer plusieurs instances derrière un répartiteur.
- **Transport Messenger interchangeable** : Doctrine au MVP. Le passage à Redis ou RabbitMQ se fait par configuration, sans toucher au code. Il faut des files séparées (`ingest`, `matching`, `notifications`, `sync`) pour scaler les workers séparément.
- **Matching incrémental** : index inverse `(écosystème, nom) → composants`. Une nouvelle advisory ne recalcule que les composants concernés, jamais tout le parc.
- **Base** :
  - index sur les clés de matching ;
  - partitionnement par date prévu pour `snapshot` et `audit_log`, les tables qui grossissent ;
  - purge par rétention (90 j) en tâche planifiée ;
  - SBOM bruts compressés, éventuellement sortis de la base vers un stockage objet (S3 compatible) au-delà du MVP.
- **Mesures dès le départ** : nombre d'agents actifs, latence d'ingestion, taille des files, durée du matching. On saura ainsi quand passer à l'étape suivante.

**Passage à 2 000 agents** :
- long polling ;
- transport Redis ou RabbitMQ ;
- N workers par file ;
- plusieurs instances de console ;
- stockage objet pour les SBOM.

Aucun changement de modèle de données ni de protocole agent n'est nécessaire.

## 10. Périmètre MVP

1. Console : comptes locaux (mot de passe + second facteur TOTP ou code email, passkey optionnelle), comptes « notification seule », invitations, équipes multiples avec quotas, rôles d'équipe et de projet (§7bis), projets, environnements, hôtes multi-projets et projets multi-hôtes (§5bis).
2. Enrôlement d'agent complet : jeton unique et jeton réutilisable (autoscaling), appairage, validation humaine, épinglage de clé, requêtes signées.
2bis. Inventaire toutes les 6 h + à la demande + à chaque changement d'image, historique de 90 jours (réglable par équipe).
3. Agent Linux/systemd : paquets OS, PHP/Composer, Node, runtimes, découverte automatique et chemins déclarés.
4. Agent mode `container` : image officielle sans script, proxy Docker en lecture seule, portées `compose` / `labeled` / `host`, labels `dev.depverify.*`. Couvre aussi ECS sur EC2 en service `DAEMON`. Images analysées par digest, plus lecture ciblée des fichiers dans les conteneurs (§6bis). L'agent `host` couvre aussi Docker si activé.
5. Synchro OSV + endoflife.date + KEV + EPSS. Matching et Findings.
6. Dashboard par projet et environnement : dépendances, versions, vulnérabilités, fins de vie, obsolescence.
7. Notifications email et webhook, règles par projet, digest, seuils, agent muet, acceptation de risque.
8. Journal d'audit en ajout seul.
9. Ordres signés : `SCAN_NOW`, `SET_CONFIG`.

## 11. Roadmap après le MVP

- **API publique complète** (lecture + écriture) avec jetons d'API, en même temps que les sources CI et Git. Les permissions `apitoken.manage` et les règles des jetons (§7bis) sont déjà prévues dans le modèle.
- **Collecteur ECS Fargate** (mode `ecs`, §6bis), avec accès aux registres privés (ECR, puis GHCR, GitLab…), puis autres plateformes managées.
- **Mode hors ligne (air-gap), envisagé pour la V1** : miroir ou import manuel des bases OSV, endoflife.date, KEV et EPSS, pour une instance sans accès Internet. L'import manuel des releases de l'agent existe déjà.
- **Autres sources d'inventaire** (prioritaires après le MVP) : API GitHub/GitLab (lecture seule), envoi de SBOM depuis la CI, upload manuel de fichiers. Le modèle `InventorySource` les prévoit dès le départ (§5, §5bis).
- Écosystèmes : Python, Ruby, Java, Go ; Kubernetes (DaemonSet) ; hébergement mutualisé (agent one-shot en cron utilisateur).
- SSO OIDC.
- Création de tickets (Jira, GitLab, GitHub) et PR de mise à jour.
- Détection des écarts entre environnements (prod ≠ preprod ≠ repo).
- Proxy Docker maison `ghcr.io/dependencyverifier/docker-proxy`, qui filtre par projet Compose et par label, pour une isolation technique entre projets d'un même hôte.
- Export SBOM / VEX, rapports PDF par équipe ou par projet, aide aux dossiers NIS2.

## 12. Questions ouvertes

- Marque : vérification de « DependencyVerifier » à l'INPI et à l'EUIPO (classes 9 et 42). Le nom est descriptif, donc difficile à protéger, et proche de la *dependency verification* de Gradle. L'organisation GitHub `DependencyVerifier` existe depuis le 08/11/2026.
- **Bibliothèque WebAuthn** : à choisir à l'implémentation de l'authentification (support natif Symfony s'il existe à ce moment-là, sinon `web-auth/webauthn-framework`).
