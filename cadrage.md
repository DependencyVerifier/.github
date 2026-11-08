# DepRadar — Surveillance des dépendances et CVE par agent

> Nom du projet : **DepRadar**. Identifiant technique `depradar` : console `depradar`, agent `depradar-agent`, image `ghcr.io/depradar/agent`, préfixe des labels Docker `dev.depradar.*`.
> Document de cadrage destiné à servir de contexte de travail (humain ou IA) pour la conception et le développement.
> Auteur : Romain Millan — dernière mise à jour : 08/11/2026 (ajouts : authentification par passkey, design de la console, architecture DDD, healthcheck).

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
| Dépassement de quota | **Blocage strict.** |
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
| Design de la console | Interface **sobre et dense, inspirée de shadcn/ui** : sidebar à gauche, en-têtes d'objet, cartes de métadonnées, onglets, thème clair / sombre / système. **Symfony UX Toolkit (kit `shadcn`) + Tailwind CSS v4**, compilé par Vite via Symfony Reprise. Polices auto-hébergées (voir §9 et `docs/design.md`). |
| Autoscaling | **Jeton d'enrôlement réutilisable**, validé une fois par un humain, limité en nombre d'agents et dans le temps. Les agents enrôlés avec ce jeton sont validés automatiquement (voir §6). |
| Mode `embedded` | **Hors MVP**, ajouté quand un besoin réel apparaît. |
| Registres d'images applicatives | **Aucun accès registre au MVP, quelle que soit l'origine de l'image** : GitHub Container Registry, registre privé ou **image construite sur le serveur** avec un Dockerfile. Dès qu'un conteneur tourne, son image est présente dans le moteur Docker local, et l'agent la lit via l'API Docker. Il n'a besoin d'aucun identifiant de registre. L'accès aux registres n'arrivera qu'avec le collecteur Fargate (voir §6bis, « Identité d'une image »). |
| Distribution de l'agent | **GitHub public** : binaires (GitHub Releases, signés minisign) et image Docker (`ghcr.io`, signée cosign), utilisables par tous. La console vérifie les signatures avant de servir une version. **Import manuel** d'un binaire signé possible pour les instances sans accès Internet. |
| Dimensionnement | **Cible MVP ≤ 200 agents** par instance. Le design doit permettre de monter à **≤ 2 000 agents** sans refonte (voir §9bis). |
| Fréquence d'inventaire | **Toutes les 6 h + à la demande** (`SCAN_NOW`), et immédiatement à chaque changement d'image détecté en conteneur. **Historique de 90 jours**, puis seul le dernier état est conservé. Réglable par équipe. |

## 4. Architecture d'ensemble

```
 Serveur supervisé                               Instance self-hosted   
┌──────────────────────────┐                ┌──────────────────────────────────┐
│  depradar-agent (Rust)   │   HTTPS sortant│  Console                         │
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
- **User** : email, hash Argon2id (nullable), second facteur (secret TOTP chiffré, nullable ; à défaut, code par email), passkeys (voir PasskeyCredential), statut, `roles` (rôles Symfony, voir §7bis), `loginEnabled`.
  - **Compte complet** : `loginEnabled = true`, se connecte à la console.
  - **Compte « notification seule »** : `loginEnabled = false`, sans mot de passe. Il reçoit les notifications des projets auxquels il est rattaché, avec un email vérifié par lien de confirmation et un lien de désinscription signé. Un `UserChecker` Symfony refuse toute connexion. Il peut être **promu** plus tard en compte complet par invitation, sans perdre ses rattachements.
- **PasskeyCredential** (appartient à un User, 0..N) : `uuid`, identifiant du credential WebAuthn, clé publique, compteur de signatures, transports, AAGUID, **nom** donné par l'utilisateur (« YubiKey bureau », « iCloud »…), dates de création et de dernière utilisation. Révocable individuellement par son propriétaire (et par le super admin). Enregistrement et révocation tracés dans l'audit.
- **EmailLoginCode** : code à usage unique du second facteur par email, stocké **haché**, expiration courte (~10 min), nombre d'essais limité, invalidé dès usage ou à l'émission d'un nouveau code.
- **Team** : `uuid`, `name`, `slug`, **quotas** (`maxProjects`, `maxAgents`, `maxMembers`, `maxEnvironmentsPerProject`, rétention des snapshots…), initialisés depuis les quotas par défaut de l'instance. Une valeur nulle signifie illimité. Les quotas sont modifiables uniquement par le super admin.
  - **Blocage strict** : toute action qui dépasserait un quota est refusée. C'est le cas de la création d'un projet, d'un environnement, d'un jeton d'enrôlement, de la validation d'un agent ou d'une invitation. Le message d'erreur est explicite et l'admin de l'équipe est invité à contacter le super admin.
  - Si le super admin baisse un quota sous l'usage actuel, rien n'est supprimé, mais toute nouvelle création est bloquée tant que l'équipe est au-dessus de la limite.
- **TeamMembership** (`user`, `team`, `role` : `TEAM_ADMIN` / `TEAM_MEMBER` / `TEAM_VIEWER` / `TEAM_GUEST`, `extraPermissions[]`). Un utilisateur peut avoir des memberships dans plusieurs équipes.
- **ProjectMembership** (`user`, `project`, `role` : `PROJECT_ADMIN` / `PROJECT_MEMBER` / `PROJECT_VIEWER`, `extraPermissions[]`). Elle sert aux utilisateurs limités à certains projets d'une équipe.
- **PermissionGrant** (historique) : qui a accordé ou retiré quelle permission, à qui, sur quel périmètre, quand. Aussi tracé dans l'audit.

> **Invariant** : une ProjectMembership exige une TeamMembership dans l'équipe du projet. Retirer quelqu'un d'une équipe supprime ses ProjectMemberships dans cette équipe.
- **Invitation** : email, équipe ou projet cible, rôle, jeton haché, expiration, usage unique.
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
| `maxMembers` | Comptes **complets** membres de l'équipe (memberships d'équipe ou de projet) | 25 | invitation, ajout d'un membre |
| `maxNotificationOnlyAccounts` | Comptes « notification seule » rattachés à l'équipe | 50 | ajout d'un destinataire |
| `maxNotificationChannels` | Canaux (webhooks, Slack, Teams…) de l'équipe et de ses projets | 5 | création de canal |
| `maxReusableEnrollmentTokens` | Jetons d'enrôlement réutilisables **actifs** | 3 | création de jeton réutilisable |
| `snapshotRetentionDays` | Durée de conservation de l'historique des inventaires | 90 | *(plafond : l'équipe peut réduire, pas augmenter)* |
| `minScanIntervalMinutes` | Fréquence maximale de l'inventaire automatique : l'équipe peut espacer librement (6 h, 24 h…) mais **pas descendre sous ce plancher** | 60 (1×/heure) | réglage plus fréquent refusé. Le super admin peut l'abaisser pour une équipe, par ex. à 15 min. `SCAN_NOW` reste possible, limité à 1 par agent toutes les 5 min. |

Comportement :
- **Blocage strict à 100 %** : l'action est refusée par le service métier, que la demande vienne de l'UI ou d'un agent, avec un message explicite (« Quota de 25 agents atteint, contactez l'administrateur de l'instance »).
- **Avertissement à 80 %** : bandeau pour les admins de l'équipe et notification optionnelle au super admin. C'est une information, sans blocage.
- Les admins de l'équipe voient leur **consommation** (jauges) dans les paramètres de l'équipe.
- Le super admin n'est pas soumis aux quotas, mais les actions qu'il fait **dans** une équipe consomment le quota de cette équipe.
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
| Purge des agents `inactive` | 30 jours après passage en `inactive` |

## 6. L'agent

### Langage et distribution

- **Rust**, binaire statique (cible `*-unknown-linux-musl`), `x86_64` et `aarch64`, compilé avec `cargo-zigbuild` ou `cross`.
- Crates pressenties :
  - réseau et crypto : `rustls` (pas d'OpenSSL), `ed25519-dalek`, `minisign-verify` ;
  - analyse des fichiers : `serde_json`, `serde_yaml` ;
  - Docker et format de sortie : `bollard`, `cyclonedx-bom` ;
  - exécution : `tokio`.
- Releases **signées minisign** par la CI du projet, avec un fichier de checksums signé. Images Docker signées cosign.
- Publication **publique sur GitHub** : binaires via GitHub Releases (minisign), image `ghcr.io/depradar/agent` (cosign). Tout le monde peut les utiliser.
- La console télécharge les releases depuis GitHub (ou les reçoit par **import manuel** d'un binaire signé, pour une instance sans Internet), vérifie leur signature, puis sert `install.sh` et un miroir des binaires vérifiés.
- Plus tard : paquets `.deb` / `.rpm` dans un dépôt signé.

### Installation

```sh
curl -fsSL https://console.example.com/install.sh | AGENT_TOKEN=xxxx sh
```

1. Le jeton passe par une variable d'environnement, pas en argument, pour limiter l'exposition dans `ps` et l'historique. Il est à usage unique et expire en ~1 h.
2. Le script télécharge le binaire, vérifie son SHA-256, crée l'utilisateur système `depradar-agent`, installe l'unité systemd (durcie : `ProtectSystem=strict`, `NoNewPrivileges`, `ReadOnlyPaths`…) et lance l'enrôlement.

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
- Agents disparus (instance détruite) : après 7 jours sans remontée, ils passent en `inactive` et ne comptent plus dans le quota. Ils sont purgés 30 jours plus tard (limites d'instance, §5ter).

C'est la **seule** exception à la validation humaine individuelle. Elle est explicite, bornée et tracée.

### Communication

- **Sortante uniquement**, HTTPS, aucun port ouvert, compatible avec un proxy HTTP.
- Chaque requête est **signée** par la clé de l'agent sur méthode, chemin, horodatage et hash du corps (inspiration : HTTP Message Signatures, RFC 9421). Aucun secret partagé ne transite.
- L'agent récupère ses ordres par **polling**. L'intervalle est **dicté par la console** dans chaque réponse, avec gestion de `429` / `Retry-After` et un jitter aléatoire. Le protocole est prêt pour le long polling (voir §9bis).

### Ordres (catalogue fermé)

Tous les ordres sont signés Ed25519 par la console et portent un id unique et une fenêtre de validité courte. L'agent garde une mémoire anti-rejeu persistée, qui survit au redémarrage.

| Ordre | Effet |
|---|---|
| `SCAN_NOW` | Relance un inventaire complet |
| `SET_CONFIG` | Racines de découverte, chemins déclarés, exclusions, intervalle |
| `UPGRADE_AGENT` *(post-MVP)* | Mise à jour vers une version donnée. Le binaire est vérifié avec la **clé de release du projet**, pas celle de la console. |
| `ROTATE_KEY` *(post-MVP)* | Régénère la paire de clés de l'agent |

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
- L'image `ghcr.io/depradar/agent` a pour `ENTRYPOINT` le binaire de l'agent.
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
- *Roadmap :* une image de proxy maison (`depradar/docker-proxy`) qui filtre par projet Compose et par label, pour une isolation technique.
- Variante « un seul service » : l'agent monte directement le socket. C'est plus simple, mais l'agent devient équivalent à root sur l'hôte. Documentée, mais **déconseillée**.

**Portée de la surveillance : `AGENT_SCOPE`**

| `AGENT_SCOPE` | Conteneurs surveillés | Usage |
|---|---|---|
| `compose` (**défaut**) | **Tous** les conteneurs de son projet Compose (détecté automatiquement via le label `com.docker.compose.project`), sauf ceux marqués `dev.depradar.monitor=false` | Cas standard : « je surveille mon projet » |
| `labeled` | **Seulement** les conteneurs de son projet Compose marqués `dev.depradar.monitor=true` | « Je ne veux surveiller que `app` et `worker`, pas `redis` ni `mailpit` » |
| `host` | **Tous** les conteneurs de l'hôte, sauf `dev.depradar.monitor=false`. Avec montage `/host:ro`, aussi l'OS de l'hôte | Un seul agent pour tout un hôte Docker, ECS sur EC2 (service `DAEMON`) |

**Labels Docker reconnus**, posés sur les services de l'application dans le `docker-compose.yml`. Ils sont tous optionnels :

| Label | Effet | Défaut |
|---|---|---|
| `dev.depradar.monitor` | `true` / `false` : inclure ou exclure ce conteneur | inclus (sauf en portée `labeled`) |
| `dev.depradar.name` | Nom affiché de l'application dans la console | nom du service Compose |
| `dev.depradar.environment` | **UUID** de l'environnement auquel rattacher ce service | environnement par défaut du jeton d'enrôlement |
| `dev.depradar.paths` | Chemins dans le conteneur où chercher `composer.lock`, `installed.json`, lockfiles Node… (séparés par des virgules) | détection automatique (`WORKDIR`, `/app`, `/var/www/html`, `/srv/app`…) |

*Préfixe en notation DNS inversée, selon la convention Docker. Il suppose l'usage du domaine `depradar.dev` : à ajuster selon le domaine réellement réservé.*

**Sécurité des labels :** un label n'est qu'une **proposition**. La console vérifie que l'environnement visé appartient bien à l'équipe de l'agent, sinon elle refuse et le trace dans l'audit. Un rattachement à un environnement autre que celui par défaut du jeton peut exiger une validation de l'admin (réglage d'équipe).

**Exemple complet**, généré par la console avec le jeton et l'image épinglée par digest :

```yaml
services:
  app:
    image: registry.example.com/mon-projet/app:1.4.2
    labels:
      dev.depradar.name: "API publique"
      dev.depradar.paths: "/var/www/api"
  worker:
    image: registry.example.com/mon-projet/app:1.4.2
    labels:
      dev.depradar.name: "Worker Messenger"
  redis:
    image: redis:7.4
    labels:
      dev.depradar.monitor: "false"      # exclu de la surveillance
  mailpit:
    image: axllent/mailpit
    labels:
      dev.depradar.monitor: "false"

  monitoring-agent:
    image: ghcr.io/depradar/agent@sha256:<digest>      # épinglé par digest, signé cosign
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
- Pour chaque conteneur retenu, l'agent récupère le **digest de l'image**, l'analyse **une fois** (cache par digest), puis lit en ciblé les fichiers d'inventaire dans le conteneur en cours (API `archive`, voir la nuance plus haut). Les labels `dev.depradar.paths` orientent cette lecture.
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
- volume d'état sur l'instance (`/var/lib/depradar-agent`) ;
- en autoscaling, utiliser un **jeton d'enrôlement réutilisable** (voir §6).

#### 3. Agent embarqué dans l'image de l'application (`embedded`, secours, hors MVP)

Possible quand on ne peut ni installer sur l'hôte, ni accéder au socket Docker (hébergeur restrictif, PaaS…) :

```dockerfile
COPY --from=ghcr.io/depradar/agent@sha256:<digest> /agent /usr/local/bin/depradar-agent
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
- La **clé privée de signature** de la console ne quitte jamais le serveur. Une procédure de rotation doit être documentée.
- **Cloisonnement** : chaque requête, chaque vue et chaque ordre vérifie que la ressource appartient au périmètre de l'utilisateur. Le contrôle est **centralisé** (voters Symfony) et pas ajouté action par action.
- **Journal d'audit** :
  - posé globalement, sur toutes les routes, UI comme API agents ;
  - qui, quoi, sur quoi, résultat, IP ;
  - refus tracés et distingués des erreurs serveur ;
  - **jamais le corps des requêtes** ;
  - en **ajout seul** (triggers PostgreSQL qui refusent `UPDATE` et `DELETE`) ;
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
  - 2FA **obligatoire pour super admin, TEAM_ADMIN et PROJECT_ADMIN** (voir §12 sur le niveau exigé) ;
  - enregistrement, révocation et usage des passkeys et du TOTP **tracés dans l'audit** ; échecs répétés limités (rate limiting par compte et par IP) ;
  - pas d'inscription libre : création de compte **sur invitation uniquement**. Pas de connexion via un fournisseur tiers (GitHub…) au MVP ;
  - sessions courtes, cookies `HttpOnly` / `Secure` / `SameSite=Strict` ;
  - *(post-MVP, avec l'API publique)* jetons d'API avec droits limités et expiration, transmis via l'en-tête `Authorization`, jamais dans l'URL.
- **Souveraineté** : aucune télémétrie. Les seuls flux sortants de la console sont les **téléchargements** des bases publiques, qui peuvent être désactivés ou, à partir de la V1, passer par un miroir (mode air-gap). L'interface ne charge **aucune ressource externe** (polices, scripts, CDN) : tout est servi par l'instance.

## 7bis. Gestion des droits

### Principes

- **3 niveaux** : instance, équipe, projet.
- **Niveau instance = rôles Symfony natifs.** `ROLE_SUPER_ADMIN` est stocké dans `User.roles`, avec une `role_hierarchy` (`ROLE_SUPER_ADMIN: [ROLE_USER]`) et utilisable via `#[IsGranted('ROLE_SUPER_ADMIN')]` et `access_control`. Les rôles Symfony sont **globaux**, ils ne peuvent pas porter « admin de l'équipe 1 mais invité dans l'équipe 3 ». Les rôles d'équipe et de projet restent donc dans les memberships, et sont évalués par des voters.
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

- Une équipe garde **au moins un `TEAM_ADMIN`**, et l'instance au moins un `ROLE_SUPER_ADMIN` actif.
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
- Un `UserChecker` refuse la connexion des comptes `loginEnabled = false`.
- Un `PermissionResolver` calcule une fois par requête les permissions effectives de l'utilisateur **par équipe et par projet**, à partir de `ROLE_SUPER_ADMIN`, des rôles et des `extraPermissions` des TeamMembership et ProjectMembership.
- Une table de correspondance unique dans le code définit, pour chaque rôle, les permissions par défaut (✓) et les permissions accordables (○). Elle sert à la fois au resolver, à l'UI d'attribution et aux tests.
- Les voters `TeamVoter`, `ProjectVoter`, `HostVoter` et `FindingVoter` délèguent au resolver.
- Les requêtes Doctrine de listing sont **filtrées par périmètre**, via un filtre ou des repositories dédiés, pour qu'une liste ne fuite jamais d'objet hors périmètre.
- Les **quotas** d'équipe sont vérifiés dans les services métier (création de projet, d'environnement, de jeton d'enrôlement, validation d'agent, invitation) et pas seulement dans l'UI. Le dépassement est **bloquant**, y compris pour un appel via l'API. Le super admin n'est pas soumis aux quotas, mais c'est lui qui les ajuste.

## 8. Moteur d'analyse

### Sources (synchronisation locale)

| Source | Usage |
|---|---|
| **OSV.dev** (exports zip par écosystème) | Vulnérabilités Packagist, npm, Debian, Ubuntu, Alpine, AlmaLinux/Rocky… La couverture RHEL est à vérifier. |
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
- **Healthcheck** : `GET /_healthcheck`. La page vient de Romain-MILLAN-Healthcheck, adaptée pour ne charger aucune ressource externe. Elle exécute des sondes (base de données…), renvoie 503 en JSON si une dépendance tombe et sert de healthcheck au conteneur.
- **Signature** : le footer affiche le tag Romain MILLAN, intégré en submodule git (`console/assets/romain-millan-tag`).
- **Domaine local de développement** : `https://console.depradar.localhost`.
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
4. Agent mode `container` : image officielle sans script, proxy Docker en lecture seule, portées `compose` / `labeled` / `host`, labels `dev.depradar.*`. Couvre aussi ECS sur EC2 en service `DAEMON`. Images analysées par digest, plus lecture ciblée des fichiers dans les conteneurs (§6bis). L'agent `host` couvre aussi Docker si activé.
5. Synchro OSV + endoflife.date + KEV + EPSS. Matching et Findings.
6. Dashboard par projet et environnement : dépendances, versions, vulnérabilités, fins de vie, obsolescence.
7. Notifications email et webhook, règles par projet, digest, seuils, agent muet, acceptation de risque.
8. Journal d'audit en ajout seul.
9. Ordres signés : `SCAN_NOW`, `SET_CONFIG`.

## 11. Roadmap après le MVP

- `UPGRADE_AGENT` (mise à jour automatique signée), `ROTATE_KEY`.
- **API publique complète** (lecture + écriture) avec jetons d'API, en même temps que les sources CI et Git. Les permissions `apitoken.manage` et les règles des jetons (§7bis) sont déjà prévues dans le modèle.
- **Collecteur ECS Fargate** (mode `ecs`, §6bis), avec accès aux registres privés (ECR, puis GHCR, GitLab…), puis autres plateformes managées.
- Mode `embedded` (agent dans l'image de l'application).
- **Mode hors ligne (air-gap), envisagé pour la V1** : miroir ou import manuel des bases OSV, endoflife.date, KEV et EPSS, pour une instance sans accès Internet. L'import manuel des releases de l'agent existe déjà.
- **Autres sources d'inventaire** (prioritaires après le MVP) : API GitHub/GitLab (lecture seule), envoi de SBOM depuis la CI, upload manuel de fichiers. Le modèle `InventorySource` les prévoit dès le départ (§5, §5bis).
- Écosystèmes : Python, Ruby, Java, Go ; Kubernetes (DaemonSet) ; hébergement mutualisé (agent one-shot en cron utilisateur).
- SSO OIDC.
- Création de tickets (Jira, GitLab, GitHub) et PR de mise à jour.
- Détection des écarts entre environnements (prod ≠ preprod ≠ repo).
- Proxy Docker maison `depradar/docker-proxy`, qui filtre par projet Compose et par label, pour une isolation technique entre projets d'un même hôte.
- Export SBOM / VEX, rapports PDF par équipe ou par projet, aide aux dossiers NIS2.

## 12. Questions ouvertes

- Réservation du nom : domaine (`depradar.dev` ou autre), organisation GitHub `depradar`, vérification des marques (INPI / EUIPO). Le préfixe des labels Docker en dépend.
- **Niveau de 2FA exigé pour les admins** : le code par email suffit-il pour la 2FA obligatoire des super admins, `TEAM_ADMIN` et `PROJECT_ADMIN`, ou faut-il exiger TOTP ou passkey pour ces rôles (le code email dépend de la sécurité de la boîte mail) ?
- **Bibliothèque WebAuthn** : à choisir à l'implémentation de l'authentification (support natif Symfony s'il existe à ce moment-là, sinon `web-auth/webauthn-framework`).
