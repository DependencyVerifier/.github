# Plan — Console step 2 : Fleet (cœur)

> Plan approuvé, copié tel quel. L'avancement et les décisions prises depuis sont dans [`console-step-2-status.md`](console-step-2-status.md).

## Contexte

L'étape 1 (Identity, Organization, Audit) est close. Fleet est le cœur du produit : sans agent enrôlé, aucun
inventaire, donc ni vulnérabilités ni fins de vie.

Le contrat avec l'agent est entièrement spécifié côté texte :
- `.github/docs/protocol.md` (normatif) ;
- schémas, exemples et vecteurs de test dans `docs/protocol/` ;
- `cadrage.md` §5, §5bis, §5ter, §6, §6bis, §7bis.

L'agent Rust, lui, est encore un squelette : il n'a ni enrôlement ni release. La console se construit donc contre le
protocole et ses vecteurs, et les tests jouent le rôle de l'agent.

**Tes choix** :
- cœur Fleet, sans installeur ni inventaire ;
- clé de la console en variable d'environnement ;
- hôtes créés automatiquement à l'enrôlement ;
- flotte visible par le rôle d'équipe.

**Hors de cette étape** :
- `install.sh` et le miroir des binaires minisign, faute de release ;
- les 3 endpoints d'inventaire, qui relèvent de l'étape Inventory ;
- `embedded` et `ecs`, ainsi que CloudScope ;
- les notifications (agent muet, en attente, auto-validé) et le long polling.

## Décisions par défaut (points ouverts de la spec, à valider avec ce plan)

1. **Jetons** :
   - format `dvet_` + 43 caractères base64url (256 bits), stocké haché par `TokenHasher` (HMAC + pepper), affiché une
     seule fois ;
   - jeton unique : 1 h, consommé au premier enrôlement réussi ;
   - jeton réutilisable : `maxUses` et expiration obligatoires (90 jours au plus), environnement par défaut
     obligatoire (§6), statut `pending → approved → revoked` ;
   - « actif » signifie non révoqué, non expiré et non épuisé.
2. **Quota `maxAgents`** :
   - l'usage compte les agents `pending` et `approved` ; un jeton inutilisé ne réserve pas de place ;
   - la limite bloque la création de jeton, l'enrôlement (409 `quota_exceeded`) et la validation.
3. **Quota `maxReusableEnrollmentTokens`** : l'usage compte les jetons réutilisables actifs.
4. **Agent enrôlé avec un jeton réutilisable encore `pending`** : il reste `pending` et sera validé individuellement.
   Seuls les enrôlements faits après la validation du jeton sont auto-validés.
5. **Statuts d'un agent** : `pending`, `approved`, `inactive`, `revoked`.
   - Refuser un agent en attente revient à le révoquer.
   - `inactive` : 7 jours sans requête. Toute requête valide le réactive, si le quota le permet.
   - Purge 30 jours après, par une commande de maintenance (`make fleet-maintain`, comme `audit-partitions`).
6. **Identité d'hôte** :
   - clé `(team, docker_engine_id)` pour un agent conteneur, `(team, machine_id_hash)` sinon ;
   - l'hôte est créé ou retrouvé à l'enrôlement ;
   - un ré-enrôlement (volume perdu) crée un nouvel agent sur le même hôte ;
   - supprimer un hôte exige qu'aucun de ses agents ne soit non révoqué.
7. **Modes** : seuls `host` et `container` (portées `compose`, `labeled`, `host`) sont acceptés. `embedded` et
   `ecs` répondent 400 `invalid_payload`.
8. **Ordres** :
   - cycle de vie `queued → delivered → executed | failed | rejected`, ou `expired` sans résultat 60 s après
     `expires_at` ;
   - l'ordre est signé à la livraison (`issued_at = now`, `expires_at = now + 15 min`), en JCS (RFC 8785) puis
     Ed25519 ;
   - un ordre expiré n'est pas relivré, on le réémet depuis l'interface ;
   - `SCAN_NOW` : 1 par agent toutes les 5 minutes ;
   - `SET_CONFIG` : configuration souhaitée par agent, `config_version` croissante. Si le poll rapporte une version
     inférieure sans ordre en cours, un nouvel ordre est mis en file. L'intervalle n'est jamais sous le
     `minScanIntervalMinutes` de l'équipe.
9. **Rythme** : `next_poll_in` vaut 60 s pour un agent en attente et 300 s pour un agent validé. Pas de long polling.
10. **Limites de débit** :
    - 60 requêtes par minute et par agent ;
    - à l'enrôlement, 20 par heure et par IP, contre la force brute sur les jetons (la spec ne dit rien).
11. **`@target-uri`** : reconstruit depuis la requête. Derrière un proxy, il faut `SYMFONY_TRUSTED_PROXIES`, à
    documenter. Jamais de redirection sous `/agent/v1`.
12. **Environnement par défaut d'un jeton actif** : il bloque la suppression de cet environnement (premier
    `EnvironmentContentProbe`).

## Fondations partagées (Shared / Organization)

- **Sodium** : `ext-sodium` ajouté à `composer.json`. Le module est déjà présent dans l'image.
- **Primitives Ed25519** : `Shared\Application\Crypto\Ed25519` (port), implémenté avec sodium dans Infrastructure.
  Il couvre :
  - la vérification d'une signature ;
  - la signature ;
  - la clé au format `ed25519:<b64>` et l'empreinte `SHA256:<b64 sans padding>` ;
  - la canonicalisation JCS.
- **`ConsoleSigningKey`** :
  - lue depuis `APP_AGENT_SIGNING_KEY` (graine base64), en échec fermé hors dev et test ;
  - valeurs de dev et de test dans `.env.dev` / `.env.test` ;
  - sa clé publique et son empreinte sont affichées dans l'interface.
- **Acteur `Agent`** :
  - `ActorType::Agent` ;
  - un utilisateur de sécurité qui expose son acteur (interface `Shared\Infrastructure\Security\ActorAwareUser`),
    lue par `AuthenticatedCurrentActor` ;
  - les écritures de l'agent sont ainsi auditées au nom de l'agent.
- **Contrats Organization** :
  - `GetTeamAccess(teamId)` renvoie l'équipe, le rôle de l'acteur et s'il est super admin (404 hors périmètre) ;
  - `GetTeamQuota(teamId, quota)` renvoie la limite ;
  - `EnvironmentOfTeam(teamId, environmentId)` dit si l'environnement existe dans l'équipe.
- **Port `QuotaUsageProvider`** :
  - tagué, implémenté par Fleet pour `max_agents` et `max_reusable_enrollment_tokens` ;
  - collecté par `GetTeamHandler`, si bien que ces jauges deviennent appliquées et que les boutons se désactivent ;
  - Fleet compte son usage sous un `TransactionLock` `fleet.team:<id>`.
- **Limiteurs** : nouveaux `ThrottleName` `AgentRequests` et `AgentEnrollmentIp`, entrées dans `rate_limiter.yaml`
  et dans le localisateur de `services.yaml`.

## Domaine Fleet (`src/Fleet/Domain`)

- **`EnrollmentToken`** : `single` ou `reusable`, équipe, environnement, hash, expiration, `maxUses`, compteur
  d'usages, statut. Méthodes : `consume()`, `approve()`, `revoke()`, `isUsableAt()`.
- **`Host`** : équipe, clé d'identité (type et valeur), nom d'hôte, OS, architecture, `lastSeenAt`.
- **`Agent`** :
  - équipe, hôte, jeton d'origine ;
  - clé publique et empreinte (uniques) ;
  - mode et portée, `compose_project`, version ;
  - statut, `lastSeenAt` ;
  - configuration souhaitée et version appliquée.
  - Méthodes : `approve()`, `revoke()`, `touch()`, `markInactive()`, `reactivate()`.
- **`AgentOrder`** : type, charge utile, statut, `issuedAt` / `expiresAt` / signature à la livraison, résultat.
- **Événements** : `AgentEnrolled`, `AgentApproved`, `AgentRevoked`, `ReusableTokenApproved`, pour l'audit et les
  futures notifications.
- **Migration** `migrations/2026/` :
  - tables `fleet_enrollment_token`, `fleet_host`, `fleet_agent`, `fleet_agent_order`, `fleet_agent_nonce` ;
  - index uniques partiels (empreinte d'un agent non révoqué, clé d'hôte par équipe) ;
  - `fleet_agent_nonce` a une clé unique `(keyid, nonce)` et une purge au-delà de 10 minutes.

## API agent (`/agent/v1`)

- **Sécurité** : pare-feu `agent` sans session ni CSRF, placé avant `main` (`^/agent/v1`), et règle `access_control`
  `PUBLIC_ACCESS`. L'authentification est faite par Fleet lui-même.
- **`AgentRequestVerifier`** (Application) suit l'ordre §4.3 du protocole :
  1. structure de la signature ;
  2. horloge à ±300 s (sinon `clock_skew` avec `server_time`) ;
  3. `Content-Digest` sur les octets reçus ;
  4. `keyid` connu, ou empreinte de la clé du corps à l'enrôlement ;
  5. signature Ed25519 ;
  6. nonce rejoué (10 minutes) ;
  7. statut de l'agent.

  Chaque échec est audité (agent, endpoint, raison, IP), jamais le corps.
- **`POST /agent/v1/enrollments`** :
  - preuve de possession par la clé envoyée, jeton vérifié sous verrou ;
  - quota, hôte créé ou retrouvé ;
  - réponse 201, ou 200 si même jeton et même clé (idempotent) ;
  - retour de `console_key_id`.
- **`POST /agent/v1/poll`** :
  - met à jour `last_seen`, la version, `config_version` et applique les `order_results` ;
  - livre les ordres en file (20 au plus, signés) si l'agent est validé ;
  - répond `next_poll_in` et `server_time`.
- **Erreurs** : `application/problem+json` avec les types `urn:depverify:problem:*`, `Retry-After` sur 429, et
  `unsupported_protocol_version` si la version n'est pas 1.
- **Lecture des corps** : les champs inconnus sont ignorés, les schémas ne sont jamais validés à la lettre.

## Interface (groupe « Team » de la barre latérale)

- **Hosts** (`/teams/{t}/hosts`) : liste des hôtes (nom, OS, nombre d'agents, dernière remontée) ; menu ⋯ Supprimer
  (confirmation).
- **Agents** (`/teams/{t}/agents`) :
  - liste avec point de statut, empreinte en mono, mode et portée, version, dernière remontée ;
  - menu ⋯ : Valider (dialogue qui affiche l'empreinte à comparer), Révoquer, Scan now, Configurer
    (`SET_CONFIG`), historique des ordres.
- **Enrollment** (`/teams/{t}/enrollment`) :
  - jetons actifs (type, environnement, usages, expiration, statut) ;
  - « New token » (unique ou réutilisable) en dialogue, avec le jeton affiché une seule fois
    (`SecretRevealingResponse`), la commande `docker run` / l'extrait Compose (image, `AGENT_CONSOLE_PUBKEY`,
    `AGENT_TOKEN`) et l'empreinte de la console ;
  - Valider / Révoquer un jeton réutilisable (option « révoquer aussi ses agents ») ;
  - boutons désactivés par les quotas.
- **Visibilité** : tout membre d'équipe hors `TEAM_GUEST`. Les gestes suivent `host.enroll`, `host.approve`,
  `host.revoke`, `host.delete` et `host.order` (vérifiés par les handlers). 404 hors périmètre, 403 sans permission.
- **Admin** : `/admin/agents`, vue globale (`instance.agents.view`) avec l'équipe, le statut, la version et la
  dernière remontée.
- **Vue d'ensemble de l'équipe** : les jauges `max_agents` et `max_reusable_enrollment_tokens` deviennent
  appliquées.

## Découpage en commits (un `make qa` vert avant chacun)

1. Fondations : sodium, Ed25519, JCS, `ConsoleSigningKey` et les **deux vecteurs de test reproduits octet pour
   octet**, acteur `Agent`, contrats, `QuotaUsageProvider`, limiteurs.
2. Domaine Fleet, migration, dépôts Doctrine.
3. API agent : vérificateur, enrôlement, poll, nonces, problèmes, pare-feu, audit.
4. Interface : jetons (affichage unique et extrait Compose), agents (valider, révoquer), hôtes, vue admin, jauges.
5. Ordres : `SCAN_NOW`, `SET_CONFIG`, livraison signée, résultats, expiration ; commande de maintenance (inactifs,
   purge, nonces).
6. Documentation : `cadrage.md` (décisions par défaut ci-dessus), `design.md`, statut, `console/CLAUDE.md` (contexte
   Fleet).

## Tests

- **Unitaires (Domain/Application, 100 % de MSI)** :
  - cycle de vie des jetons, agents et ordres ;
  - quotas ;
  - vérificateur (chaque refus, dans l'ordre §4.3) ;
  - signature des ordres.
- **Vecteurs du protocole** :
  - vérifier `test-vectors/request-signature.json` ;
  - signer `test-vectors/order-signature.json` et retrouver la même signature.
- **Fonctionnels** : un `Tests\Fleet\Support\AgentClient` (sodium) signe les requêtes comme l'agent et rejoue :
  1. création d'un jeton dans l'interface ;
  2. enrôlement (201), puis ré-essai (200) ;
  3. poll `pending`, puis validation dans l'interface, puis poll `approved` ;
  4. `SCAN_NOW` livré signé, résultat `executed` ;
  5. révocation, puis poll 401 `agent_revoked`.

  Ils couvrent aussi : rejeu de nonce, `clock_skew`, digest faux, jeton expiré ou réutilisé, quota atteint (409),
  isolation entre deux équipes, et le fait qu'une requête `/agent/v1` sans session ne redirige jamais.
- **Intégration** : unicité des nonces avec deux sessions, index partiels.

## Vérification

1. `make qa` vert, avec 100 % de MSI, à chaque commit.
2. Le script de validation du protocole (`.github/docs/protocol/validate.py`) passe toujours, et les vecteurs sont
   reproduits par la console.
3. Dans le navigateur (`admin@depverify.localhost`) : créer un jeton, enrôler un « agent » de test avec
   `AgentClient` (une commande `make fleet-fake-agent` pour la démo locale), le voir en attente, comparer
   l'empreinte, valider, lancer un Scan now et voir le résultat.
