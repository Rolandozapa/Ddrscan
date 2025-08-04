# Guide de déploiement gratuit : Vercel + Railway + MongoDB Atlas

## 🎯 Vue d'ensemble

Nous allons déployer votre application fullstack gratuitement sur :
- **Frontend (React)** → **Vercel**
- **Backend (FastAPI)** → **Railway** 
- **Base de données** → **MongoDB Atlas**

## 📋 Prérequis

1. Compte GitHub (pour connecter vos repositories)
2. Compte gratuit sur chaque plateforme
3. Votre code prêt (déjà fait ✅)

---

## 🗄️ Étape 1 : MongoDB Atlas (Base de données)

### 1.1 Créer un compte
1. Allez sur https://www.mongodb.com/atlas
2. Cliquez sur "Try Free"
3. Créez votre compte gratuit

### 1.2 Créer un cluster gratuit
1. Choisissez "M0 Sandbox" (gratuit)
2. Sélectionnez un provider (AWS recommandé)
3. Choisissez une région proche de vous
4. Nommez votre cluster (ex: "myapp-cluster")
5. Créez le cluster (ça prend 3-5 minutes)

### 1.3 Configuration de sécurité
1. **Database Access** :
   - Créez un utilisateur avec mot de passe
   - Donnez les permissions "Read and write to any database"
   - Notez le nom d'utilisateur et mot de passe

2. **Network Access** :
   - Ajoutez "0.0.0.0/0" (accès depuis partout)
   - Ou ajoutez les IPs de Railway si vous les connaissez

### 1.4 Obtenir la chaîne de connexion
1. Cliquez sur "Connect" dans votre cluster
2. Choisissez "Connect your application"
3. Copiez la chaîne de connexion MongoDB URI
4. Remplacez `<password>` par votre mot de passe réel

**Format :** `mongodb+srv://username:password@cluster.mongodb.net/database_name`

---

## 🚂 Étape 2 : Railway (Backend)

### 2.1 Créer un compte
1. Allez sur https://railway.app
2. Connectez-vous avec votre compte GitHub

### 2.2 Déployer votre backend
1. Cliquez sur "New Project"
2. Choisissez "Deploy from GitHub repo"
3. Sélectionnez votre repository
4. Railway détectera automatiquement que c'est du Python

### 2.3 Configuration des variables d'environnement
1. Dans votre projet Railway, allez dans "Variables"
2. Ajoutez ces variables :
   ```
   MONGO_URL=mongodb+srv://username:password@cluster.mongodb.net/database_name
   DB_NAME=your_database_name
   PORT=8000
   ```

### 2.4 Configuration du déploiement
1. Railway va automatiquement utiliser le fichier `railway.toml`
2. Votre backend sera disponible sur une URL comme : `https://your-app.railway.app`
3. Testez en visitant : `https://your-app.railway.app/api/`

---

## ⚡ Étape 3 : Vercel (Frontend)

### 3.1 Créer un compte
1. Allez sur https://vercel.com
2. Connectez-vous avec votre compte GitHub

### 3.2 Déployer votre frontend
1. Cliquez sur "New Project"
2. Importez votre repository GitHub
3. Vercel détectera automatiquement React

### 3.3 Configuration du build
1. **Root Directory** : `frontend`
2. **Build Command** : `yarn build`
3. **Output Directory** : `build`
4. **Install Command** : `yarn install`

### 3.4 Variables d'environnement
1. Dans les paramètres du projet Vercel
2. Ajoutez cette variable :
   ```
   REACT_APP_BACKEND_URL=https://your-app.railway.app
   ```
   (Remplacez par l'URL réelle de votre backend Railway)

---

## 🔗 Étape 4 : Connexion et tests

### 4.1 URLs finales
Après déploiement, vous aurez :
- **Frontend** : `https://your-project.vercel.app`
- **Backend** : `https://your-app.railway.app`
- **API** : `https://your-app.railway.app/api/`

### 4.2 Test de fonctionnement
1. Visitez votre frontend Vercel
2. Ouvrez la console du navigateur (F12)
3. Vous devriez voir "Hello World" dans les logs
4. Si pas d'erreurs = ✅ Tout fonctionne !

---

## 💡 Conseils et limites

### Plans gratuits :
- **MongoDB Atlas** : 512MB de stockage
- **Railway** : 500h d'utilisation/mois (≈ 20 jours continus)
- **Vercel** : 100GB de bande passante/mois

### Tips :
- Gardez vos URLs Railway et Vercel pour les partager
- Railway se met en veille après 30min d'inactivité (redémarre automatiquement)
- Mettez à jour `REACT_APP_BACKEND_URL` si l'URL Railway change

---

## 🆘 En cas de problème

1. Vérifiez les logs Railway dans l'onglet "Deployments"
2. Vérifiez les logs Vercel dans l'onglet "Functions"
3. Testez la connexion MongoDB avec MongoDB Compass
4. Vérifiez que les variables d'environnement sont correctes

**Votre application sera accessible 24h/24 et gratuite ! 🎉**