# Plan — Console step 3 : Inventory

> Plan approuvé, copié tel quel. L'avancement et les décisions prises depuis sont dans [`console-step-3-status.md`](console-step-3-status.md).

## Contexte

L'étape 2 a livré Fleet : jetons, enrôlement, API signée, poll et ordres. Un agent validé sait maintenant parler à la
console, mais il n'a encore rien à envoyer : les trois endpoints d'inventaire du protocole (§8) n'existent pas, et le
contexte `Inventory` est vide.

Cette étape fait entrer ce qui tourne réellement en production :
- les snapshots (faits d'hôte et SBOM CycloneDX) sont reçus, vérifiés et dédupliqués ;
- ils sont transformés en applications (AppInstance), images et paquets ;
- les applications sont rattachées aux environnements des projets ;
- tout cela est visible dans la console.

C'est le socle du matching (étape 4 : Vulnerability et Exposure), qui consommera un inventaire normalisé quelle que
soit sa source (`InventorySource`, cadrage §5 et §5bis).

**Tes choix** :
- snapshots dans **PostgreSQL** (`bytea` gzip), dédupliqués par (équipe, digest) ;
- traitement **asynchrone** : transport Messenger Doctrine, file `ingest`, service `worker` dans Compose ;
- rattachement **automatique puis manuel** ;
- interface **hôte + applications + composants**.

**Hors de cette étape** :
- matching, findings, notifications ;
- diff entre inventaires et détection de dérive ;
- sources Git, CI et upload ;
- modes `embedded` et `ecs`.

## Ajout au protocole v1 (additif, avant le code)

**Lacune** : aucun sujet ne porte les **paquets OS de l'hôte** (dpkg, rpm, apk). Les faits d'hôte ne contiennent que
l'OS, le noyau, les runtimes et Docker, alors que le cadrage (§5bis et §6) compte ces paquets parmi l'inventaire de la
machine.

**Ajout proposé** : un sujet `kind: host`, `subject_key: host`, avec un SBOM CycloneDX des paquets OS.
- Un agent `host`, ou `container` en portée `host`, l'envoie.
- Un agent `compose` ou `labeled` ne l'envoie pas : il ne voit pas l'hôte.

**À mettre à jour ensemble** :
- `protocol.md` §8.2 ;
- le schéma `inventory-manifest` ;
- l'exemple ;
- `validate.py` doit rester vert.

Le changement est additif : un agent v1 qui ne l'envoie pas reste valide.

## Décisions par défaut (points ouverts de la spec)

1. **Dédup et confidentialité** :
   - les blobs sont propres à l'équipe : clé unique (équipe, digest) ;
   - `missing` est calculé pour l'équipe de l'agent : une équipe n'apprend jamais qu'une autre détient un document.
2. **Manifeste** :
   - `inventory_id` est choisi par l'agent ; rejouer le même manifeste du même agent est idempotent (même réponse) ;
   - le même id venant d'un autre agent reçoit `invalid_payload` ;
   - un manifeste non complété en 1 h est abandonné (maintenance).
3. **Garde de portée** :
   - en portée `compose` ou `labeled`, un sujet dont `compose_project` diffère du projet enrôlé fait rejeter tout
     l'inventaire (`403 scope_violation`, audité) ;
   - c'est vérifié **dès le manifeste** (rien n'est stocké) et à nouveau à `complete`.
4. **Agent en attente** : les trois endpoints répondent `403 agent_pending`, et l'agent continue de poller.
5. **Taille** :
   - envoi d'un snapshot limité à **20 Mo compressés** : la limite de 1 Mio de l'authenticator devient une limite
     par route ;
   - décompression en flux, arrêtée à **200 Mo** (`payload_too_large`) ;
   - SHA-256 des octets décompressés égal au `{digest}`, sinon `digest_mismatch` (422) ;
   - format vérifié : CycloneDX 1.6 dont `serialNumber` et `metadata.component.bom-ref` collent au manifeste ;
     faits d'hôte en `format_version` 1. Sinon `invalid_payload`.
6. **`complete`** :
   - `409 missing_snapshots` (avec la liste) si un digest manque ;
   - sinon `202`, et un message `ProcessInventory` part dans la file `ingest`. L'API ne parse rien d'autre.
7. **Traitement** (worker, commande sous un acteur système, une transaction) :
   - faits d'hôte : runtimes et Docker sont mis à jour ;
   - un sujet `path`, `compose_service` ou `container` devient une **AppInstance**, d'identité (hôte, `subject_key`) ;
   - un sujet `container_image` devient une **ContainerImage**, d'identité (équipe, `image_id`) ;
   - un sujet `host` devient le SBOM OS de l'hôte ;
   - les paquets d'un SBOM sont extraits **une fois par (équipe, digest)** (purl, écosystème, nom, version, direct
     ou transitif, source, gestionnaire) ;
   - une application absente du dernier inventaire de son hôte devient `gone` et garde son historique.
8. **Rattachement** :
   - ordre : label `dev.depverify.environment`, s'il désigne un environnement de l'**équipe** (`FindTeamEnvironment`) ;
     sinon l'environnement par défaut du jeton si l'hôte ne porte qu'**une** application ; sinon « non rattachée » ;
   - le rattachement manuel (`project.apps.assign` sur le projet cible) n'est **jamais** écrasé par l'automatique ;
   - l'équipe de l'hôte doit être celle de l'environnement : vérifié par le handler, et par une contrainte en base
     sur les ids d'équipe.
9. **Historique** :
   - un snapshot horodaté par sujet et par inventaire ;
   - purge au-delà de `snapshotRetentionDays` en gardant le dernier de chaque sujet ; blobs orphelins supprimés ;
   - commande `make inventory-maintain`.
10. **Visibilité** :
    - un membre de l'équipe (hors `TEAM_GUEST`) voit tous les hôtes, applications et images ;
    - un `TEAM_GUEST` voit, dans les projets qu'il voit, leurs applications, et la page des hôtes qui les portent
      (faits et paquets OS) ;
    - il ne voit jamais les applications des autres projets, ni Agents ni Enrollment.
11. **Contrats** :
    - Inventory interroge Fleet par `GetAgentContext(agentId)` : équipe, hôte, statut, mode, portée, projet Compose,
      environnement par défaut du jeton ;
    - Fleet affiche l'inventaire d'un hôte en interrogeant Inventory (requêtes de l'UI, contexte UI).

## Fondations (Shared, Fleet, infra)

- **Messenger asynchrone** :
  - transport `ingest` en `doctrine://default?queue_name=ingest&use_notify=true` (LISTEN/NOTIFY) ;
  - transport `failed` ;
  - migration de la table `messenger_messages` ;
  - routage de `ProcessInventory` vers `ingest` ;
  - `sync://` en test (le traitement s'exécute dans le test).
- **Service Compose `worker`** : même image que `php`, commande
  `messenger:consume ingest --time-limit=3600 --memory-limit=256M`, redémarrage automatique.
  - En dev, cible `make worker-logs`.
  - Le healthcheck de `php` ne change pas.
- **Fleet** :
  - contrat `GetAgentContext` ;
  - nouveaux problèmes `scope_violation` (403), `missing_snapshots` (409, champ `missing`), `digest_mismatch` (422) ;
  - limite de corps par route dans `AgentRequestAuthenticator` ;
  - `AgentClient` de test : `PUT` gzip et requête `complete`.

## Domaine Inventory (`src/Inventory/Domain`)

- **`InventoryRun`** : l'inventaire d'un agent.
  - Champs : id = `inventory_id`, agent, équipe, hôte, déclencheur, fenêtre de collecte, sujets du manifeste
    (valeur), statut.
  - Statuts : `open → completed → processed`, ou `rejected` / `discarded`.
  - Méthodes : `missingAmong()`, `complete()`, `markProcessed()`, `discardIfStale()`.
- **`SnapshotBlob`** : équipe, digest, type de média, taille, contenu gzip ; jamais modifié.
- **`HostInventory`** : hôte (id Fleet), équipe, derniers faits (runtimes, Docker, OS), digest du SBOM OS, date.
- **`AppInstance`** :
  - champs : équipe, hôte, `subject_key`, type, attributs (chemin, origine, runtime, service Compose, conteneurs,
    image), environnement, mode de rattachement (`auto` / `manual` / `none`), statut (`present` / `gone`), digest
    courant, date de dernière vue ;
  - méthodes : `assign()`, `unassign()`, `autoAssign()` (ignorée si manuel), `seen()`, `markGone()`.
- **`ContainerImage`** : équipe, `image_id`, tags, `repo_digests`, provenance, image de base, digest courant.
- **`SnapshotRecord`** : historique (inventaire, sujet, digest, date).
- **`Package`** : ligne par (blob, purl), lecture seule après extraction ; index sur (écosystème, nom) pour le
  matching.
- **Migration** `migrations/2026/` :
  - tables `inventory_run`, `inventory_blob`, `inventory_host`, `inventory_app_instance`, `inventory_container_image`,
    `inventory_snapshot`, `inventory_package` ;
  - index uniques (équipe, digest), (hôte, `subject_key`), (équipe, `image_id`) ;
  - suppression en cascade des paquets avec leur blob.
- **Effacement** : `TeamContentEraser` (une équipe supprimée emporte son inventaire). `ProjectContentProbe` empêche de
  supprimer un environnement qui porte des applications.

## API agent (Inventory UI, derrière le pare-feu `agent`)

| Endpoint | Commande | Réponse |
|---|---|---|
| `POST /agent/v1/inventories` | `SubmitManifest` | 200 `{inventory_id, missing, next_poll_in, server_time}` |
| `PUT /agent/v1/inventories/{id}/snapshots/{digest}` | `StoreSnapshot` | 201, ou 200 si déjà stocké |
| `POST /agent/v1/inventories/{id}/complete` | `CompleteInventory` | 202 |

- **Lecture du manifeste** : `AgentPayload` (champs inconnus ignorés), les quatre types de sujets plus `host`,
  `subject_key` et digests validés.
- **Audit** :
  - rejets audités (`scope_violation`, `digest_mismatch`…) ;
  - succès : un manifeste et un `complete` par inventaire, mais **pas** un envoi par snapshot (sans intérêt et
    volumineux).

## Traitement (`ProcessInventory`, worker)

- **Lecture CycloneDX** (`CycloneDxReader`) :
  - composants avec `purl` ;
  - propriétés `depverify:*` ;
  - écosystème déduit du purl (`composer`, `npm`, `deb`, `rpm`, `apk`) ;
  - composants sans purl ignorés et comptés.
- **Idempotent** : traiter deux fois le même inventaire ne crée rien de plus.
- **Événement** `InventoryProcessed` publié pour le matching de l'étape 4.

## Interface

- **Fleet** :
  - page hôte `/teams/{t}/hosts/{h}` : faits (OS, noyau, runtimes, Docker), paquets OS (DataTable, recherche),
    applications portées, historique des inventaires ;
  - le nom d'hôte de la liste ouvre cette page.
- **Section d'équipe « Applications »** : toutes les applications, avec un filtre « Non rattachées » et le menu ⋯
  Rattacher (dialogue Projet / Environnement) et Détacher.
- **Section de projet « Applications »** : les applications par environnement (hôte, chemin ou service, runtime,
  image, dernière vue) ; une application `gone` est grisée.
- **Page application** : identité, hôte, environnement, image, composants (purl, version, direct ou transitif,
  gestionnaire ; recherche), historique.
- **Page image** : identité (tags, digests, provenance), composants, applications qui l'exécutent.
- **Le visiteur `TEAM_GUEST`** : ses projets et les hôtes de leurs applications ; le groupe Team de la barre latérale
  est inchangé pour lui.
- **Vue d'ensemble de l'équipe** : compteurs (applications, non rattachées, images).

## Faux agent

`make fleet-fake-agent a=inventory`, et `SCAN_NOW` pendant `run`, envoient un inventaire déterministe :
- faits d'hôte ;
- SBOM OS (quelques `deb`) ;
- une application Compose (quelques `composer` et `npm`) ;
- son image.

Il envoie les trois étapes (manifeste, snapshots manquants, `complete`) : un second envoi sans changement ne transmet
que le manifeste.

## Découpage en commits (un `make qa` vert avant chacun)

1. **Protocole** (dépôt `.github`) : sujet `host`, schéma, exemple, `validate.py`.
2. **Fondations** : Messenger asynchrone (`ingest`, `failed`, migration), service `worker`, `GetAgentContext`,
   nouveaux problèmes, limite de corps par route.
3. **Domaine Inventory**, migration et dépôts Doctrine.
4. **API agent d'inventaire** : manifeste, envoi, `complete`, garde de portée, `agent_pending`, audit.
5. **Traitement** (`ProcessInventory`, CycloneDX, rattachement, paquets) et maintenance (`inventory-maintain`).
6. **Interface** : page hôte, sections Applications (équipe et projet), pages application et image, rattachement,
   visibilité du `TEAM_GUEST`.
7. **Faux agent** d'inventaire et **documentation** : `cadrage.md` (décisions 35 et suivantes), `design.md`, plan et
   statut du step 3, `CLAUDE.md`.

## Tests

- **Unitaires** (Domain et Application, 100 % de MSI) :
  - cycle de vie d'un inventaire, missing, idempotence ;
  - garde de portée ;
  - règles de rattachement (label, unique application, manuel jamais écrasé, équipe) ;
  - lecture CycloneDX (purl, écosystèmes, propriétés, sans purl) ;
  - `gone` et rétention.
- **Exemples du protocole** : `inventory-manifest.json` et les problèmes sont lus tels quels.
- **Fonctionnels** (`AgentClient`) :
  - manifeste → `missing` → `PUT` gzip → `complete` → applications, image et paquets visibles dans l'interface ;
  - second inventaire identique : `missing` vide ;
  - refus : `digest_mismatch`, gzip piégé au-delà de 200 Mo, `scope_violation`, `agent_pending`,
    `missing_snapshots`, autre équipe ;
  - rattachement manuel ;
  - vue d'un `TEAM_GUEST`.
- **Intégration** :
  - transport `ingest` réel (message envoyé, puis consommé par `messenger:consume --limit=1`) ;
  - unicités ;
  - cascade des paquets.

## Vérification

1. `make qa` vert, avec 100 % de MSI, à chaque commit. `validate.py` reste vert.
2. `docker compose up -d worker`, puis `make fleet-fake-agent a=inventory` :
   - l'inventaire passe de « completed » à « processed » ;
   - la page hôte montre les faits et les paquets OS ;
   - l'application est rattachée à l'environnement du jeton ;
   - ses composants s'affichent.
3. Un second envoi ne transmet aucun snapshot. Un `TEAM_GUEST` du projet voit l'application et son hôte, et rien
   d'autre.
