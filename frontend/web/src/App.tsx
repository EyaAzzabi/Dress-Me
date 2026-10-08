import "./styles.css";

const features = [
  {
    number: "01",
    icon: "✧",
    title: "Ton dressing, enfin organisé",
    description:
      "Retrouve toutes tes pièces au même endroit, classe-les par couleur, saison et occasion, et redécouvre ce que tu possèdes déjà.",
    tone: "rose",
  },
  {
    number: "02",
    icon: "◈",
    title: "Des looks faits pour toi",
    description:
      "Des idées de tenues selon ton style, la météo tunisienne, ton agenda et les moments qui comptent vraiment.",
    tone: "blue",
  },
  {
    number: "03",
    icon: "♡",
    title: "Achète avec intention",
    description:
      "Avant de craquer, découvre si une pièce s’accorde à ton dressing actuel, ta palette et ton budget réel.",
    tone: "gold",
  },
];

const steps = [
  {
    number: "01",
    title: "Scanner ton dressing",
    text: "Upload tes pièces, photo ou liste, pour créer une garde-robe intelligente à portée de main.",
  },
  {
    number: "02",
    title: "Apprendre ton style",
    text: "DressMe analyse tes préférences, couleurs, silhouettes et occasions favorites pour te connaître.",
  },
  {
    number: "03",
    title: "Créer des looks",
    text: "Le système propose des tenues cohérentes selon la météo, ton emploi du temps et ta personnalité.",
  },
  {
    number: "04",
    title: "Acheter mieux",
    text: "Avant tout achat, tu vois si la pièce a réellement sa place dans ton style et tes besoins.",
  },
];

const stats = [
  { value: "2x", label: "plus rapide à choisir ta tenue" },
  { value: "94%", label: "de cohérence style/occasion" },
  { value: "24°", label: "météo moyenne à Tunis" },
  { value: "365", label: "jours pour capitaliser ton dressing" },
];

function ArrowIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20" fill="none">
      <path d="M4 10h11M10 5l5 5-5 5" />
    </svg>
  );
}

function MedinaIllustration() {
  return (
    <svg
      className="medina-scene"
      viewBox="0 0 640 620"
      role="img"
      aria-label="Illustration d'une médina tunisienne au coucher du soleil"
    >
      <defs>
        <linearGradient id="medinaSky" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#ffe3e8" />
          <stop offset="1" stopColor="#f7a6bd" />
        </linearGradient>
        <linearGradient id="archFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#fff8f2" />
          <stop offset="1" stopColor="#fce7e2" />
        </linearGradient>
      </defs>
      <path
        d="M78 568V260C78 105 191 24 320 24s242 81 242 236v308H78Z"
        fill="url(#medinaSky)"
      />
      <circle cx="435" cy="150" r="58" fill="#ffe2a6" opacity=".9" />
      <path
        d="M78 427c77-66 129-82 202-50 74-46 155-42 282 11v180H78V427Z"
        fill="#d8839c"
        opacity=".5"
      />
      <path
        d="M78 466c82-50 134-51 213-14 78-34 161-31 271 7v109H78V466Z"
        fill="#fff2e9"
      />
      <path d="M132 451V316h82v135h-82Z" fill="#f8d0ca" />
      <path d="M147 316v-22h51v22" fill="#f1c1b9" />
      <path d="M159 450v-51a14 14 0 0 1 28 0v51" fill="#d9828e" />
      <path d="M244 445V359h67v86h-67Z" fill="#f5c6bd" />
      <path d="M258 359v-18h39v18" fill="#edb9b0" />
      <path d="M265 445v-31a12 12 0 0 1 24 0v31" fill="#d9828e" />
      <path d="M384 451V318h90v133h-90Z" fill="#f8d0ca" />
      <path d="M401 318v-24h56v24" fill="#efb8ae" />
      <path d="M412 451v-49a17 17 0 0 1 34 0v49" fill="#d9828e" />
      <path d="M489 446V367h60v79h-60Z" fill="#f2beb8" />
      <path d="M501 446v-29a12 12 0 0 1 24 0v29" fill="#d9828e" />
      <path d="M337 442V211h56v231h-56Z" fill="#fff8f2" />
      <path d="M328 213h74l-37-58-37 58Z" fill="#e99aa4" />
      <path d="M347 155h36v-18h-36v18Z" fill="#fff8f2" />
      <path d="M355 137v-30h20v30" fill="#fff8f2" />
      <path d="M351 107h28l-14-30-14 30Z" fill="#e99aa4" />
      <path d="M350 254h30" stroke="#e99aa4" strokeWidth="5" strokeLinecap="round" />
      <path d="M350 277h30" stroke="#e99aa4" strokeWidth="5" strokeLinecap="round" />
      <path d="M350 300h30" stroke="#e99aa4" strokeWidth="5" strokeLinecap="round" />
      <path d="M350 323h30" stroke="#e99aa4" strokeWidth="5" strokeLinecap="round" />
      <path d="M321 479c-9-81-33-117-66-139 42 8 70 35 80 86" fill="#5d8c75" />
      <path d="M334 482c-3-76 15-124 56-156-13 40-17 83-13 156" fill="#769b79" />
      <path d="M522 496c-4-68-23-97-50-116 35 4 57 28 65 71" fill="#7da282" />
      <path d="M534 497c-2-62 13-101 47-126-11 33-14 67-11 126" fill="#61866c" />
      <path d="M78 520c115-22 259-21 484 0v48H78v-48Z" fill="#f7e2d5" />
      <path d="M112 541h416" stroke="#e9c9b7" strokeWidth="2" strokeDasharray="5 10" />
    </svg>
  );
}

function App() {
  return (
    <div className="site-shell">
      <header className="site-header">
        <a className="brand" href="#accueil" aria-label="DressMe, accueil">
          <img src="/dressme-logo.png" alt="DressMe — A smarter wardrobe for a brighter you" />
        </a>
        <nav className="main-nav" aria-label="Navigation principale">
          <a href="#fonctionnalites">Découvrir</a>
          <a href="#inspiration">Notre inspiration</a>
          <a href="#comment-ca-marche">Comment ça marche</a>
        </nav>
        <div className="header-actions">
          <a className="login-link" href="#connexion">Se connecter</a>
          <a className="button button-small" href="#decouvrir">
            Commencer <ArrowIcon />
          </a>
        </div>
      </header>

      <main>
        <section className="hero section-wrap" id="accueil">
          <div className="hero-copy">
            <div className="eyebrow">
              <span className="eyebrow-star">✦</span>
              Pensé en Tunisie, imaginé pour toi
            </div>
            <h1>
              Moins de «&nbsp;je n’ai rien à me mettre&nbsp;».
              <span>Plus de looks qui te ressemblent.</span>
            </h1>
            <p className="hero-description">
              Ton dressing mérite mieux que le désordre. Découvre une façon plus
              simple, plus inspirée et plus responsable de t’habiller chaque jour.
            </p>
            <div className="hero-actions" id="decouvrir">
              <a className="button" href="#fonctionnalites">
                Découvrir DressMe <ArrowIcon />
              </a>
              <a className="text-link" href="#comment-ca-marche">
                Comment ça marche <span aria-hidden="true">↗</span>
              </a>
            </div>
            <div className="hero-note">
              <span className="note-sparkle">✧</span>
              Une touche de style, un petit geste pour la planète.
            </div>
          </div>

          <div className="hero-art" id="inspiration">
            <div className="art-halo" />
            <div className="art-arch">
              <MedinaIllustration />
              <div className="arch-stamp">صنع بحب <span>✦</span></div>
            </div>
            <div className="look-card">
              <div className="look-card-top">
                <div>
                  <span className="look-caption">TON INSPIRATION DU JOUR</span>
                  <strong>Douceur de Sidi Bou</strong>
                </div>
                <span className="heart">♡</span>
              </div>
              <div className="look-items" aria-label="Tenue du jour">
                <div className="look-item garment">
                  <span>👗</span>
                </div>
                <div className="look-item bag">
                  <span>👜</span>
                </div>
                <div className="look-item shoes">
                  <span>👡</span>
                </div>
              </div>
              <div className="look-card-bottom">
                <span>3 pièces de ton dressing</span>
                <span className="look-arrow">↗</span>
              </div>
            </div>
            <div className="float-tag weather-tag">
              <span>☀</span> 24° à Tunis
            </div>
            <div className="float-tag zellige-tag">
              <span>✦</span> Style &amp; soleil
            </div>
            <span className="flower flower-one">✿</span>
            <span className="flower flower-two">✳</span>
            <span className="hero-sparkle sparkle-one">✦</span>
            <span className="hero-sparkle sparkle-two">✧</span>
          </div>
        </section>

        <section className="inspiration-strip section-wrap" aria-label="Notre promesse">
          <div className="strip-pattern" aria-hidden="true">✦　❋　✦　❋　✦</div>
          <p>Le chic d’ici, le style qui va partout.</p>
          <div className="strip-city">
            <span>تونس</span> Tunis · Sidi Bou · partout
          </div>
        </section>

        <section className="stats-strip section-wrap" aria-label="Chiffres clés DressMe">
          <div className="stats-grid">
            {stats.map((stat) => (
              <div key={stat.label} className="stat-card">
                <strong>{stat.value}</strong>
                <span>{stat.label}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="showcase section-wrap" id="comment-ca-marche">
          <div className="showcase-panel">
            <div className="showcase-copy">
              <div className="eyebrow"><span className="eyebrow-star">✦</span> Ce que DressMe fait pour toi</div>
              <h2>Un assistant style qui <span>te suit partout.</span></h2>
              <p>
                Tu ne choisis plus au hasard. DressMe analyse ton dressing, la météo, l’occasion
                et tes goûts pour te proposer des tenues cohérentes, élégantes et faciles à porter.
              </p>
              <ul className="check-list">
                <li>• Analyse ton garde-robe en quelques minutes</li>
                <li>• Propositions de looks selon l’occasion et le climat</li>
                <li>• Aide à acheter avec plus de sens et moins d’impulsivité</li>
              </ul>
            </div>

            <div className="dashboard-preview" aria-label="Aperçu du dashboard DressMe">
              <div className="dashboard-header">
                <div>
                  <span className="dashboard-tag">Style profile</span>
                  <strong>Mon dressing</strong>
                </div>
                <span className="dashboard-dot">●</span>
              </div>
              <div className="mini-grid">
                <div className="mini-card mini-rose">
                  <span>👗</span>
                  <strong>42</strong>
                  <small>pièces</small>
                </div>
                <div className="mini-card mini-gold">
                  <span>✨</span>
                  <strong>9</strong>
                  <small>looks</small>
                </div>
                <div className="mini-card mini-blue">
                  <span>☀</span>
                  <strong>24°</strong>
                  <small>Tunis</small>
                </div>
              </div>
              <div className="progress-block">
                <div className="progress-line">
                  <span>Minimal chic</span>
                  <span>82%</span>
                </div>
                <div className="progress-track">
                  <span className="progress-fill" />
                </div>
              </div>
              <div className="mini-row">
                <span>🎨 neutres</span>
                <span>✦ occasion pro</span>
              </div>
            </div>
          </div>
        </section>

        <section className="steps section-wrap" aria-label="Comment ça marche">
          <div className="section-heading">
            <div className="eyebrow"><span className="eyebrow-star">✦</span> Comment ça marche</div>
            <h2>4 étapes pour <span>une meilleure garde-robe.</span></h2>
          </div>
          <div className="steps-grid">
            {steps.map((step) => (
              <article key={step.number} className="step-card">
                <span className="step-number">{step.number}</span>
                <h3>{step.title}</h3>
                <p>{step.text}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="features section-wrap" id="fonctionnalites">
          <div className="section-heading">
            <div className="eyebrow"><span className="eyebrow-star">✦</span> Ton quotidien, en mieux</div>
            <h2>Un dressing qui te <span>comprend.</span></h2>
            <p>Tout ce qu’il faut pour trouver ton style, sans perdre du temps.</p>
          </div>
          <div className="feature-grid">
            {features.map((feature) => (
              <article className={`feature-card ${feature.tone}`} key={feature.number}>
                <div className="feature-card-top">
                  <span className="feature-icon">{feature.icon}</span>
                  <span className="feature-number">{feature.number}</span>
                </div>
                <h3>{feature.title}</h3>
                <p>{feature.description}</p>
                <a href="#decouvrir" aria-label={`Découvrir : ${feature.title}`} className="feature-link">
                  Découvrir <ArrowIcon />
                </a>
              </article>
            ))}
          </div>
        </section>
      </main>

      <footer className="site-footer">
        <div className="footer-inner section-wrap">
          <a className="footer-brand" href="#accueil">Dress<span>Me</span></a>
          <p>Avec amour, depuis la Tunisie <span>✦</span></p>
          <a className="back-top" href="#accueil">Retour en haut ↑</a>
        </div>
      </footer>
    </div>
  );
}

export default App;
