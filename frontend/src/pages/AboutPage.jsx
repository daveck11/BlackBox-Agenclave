// About page: what Agenclave is and how it relates to BlackBox.

const REPO_URL = 'https://github.com/daveck11/BlackBox-Agenclave'

const CONCEPT_MAP = [
  {
    bb: "The Chairman picks the best patch by reading the candidates. Each pick is fresh; nothing remembers which model tends to pass on which kind of work.",
    ag: 'Runs every patch against the tests and keeps the one that passes. Records each outcome per model, and routes the next task to the models with the best record.',
  },
  {
    bb: 'One endpoint for many models and agents.',
    ag: 'Sits on top of that endpoint. Built on BlackBox’s API; the live demo routes through OpenRouter since BlackBox moved to enterprise-only access in October 2026.',
  },
]

export default function AboutPage() {
  return (
    <>
      <p className="subtitle">
        Agenclave sends a bug to several coding models at once, runs each patch against the
        bug&rsquo;s tests, and keeps the one that passes. Over time it learns which models tend to
        pass on which kinds of bug and sends new bugs to those first.
      </p>

      <div className="flow about-flow">
        <span className="flow-node">issue in</span>
        <span className="flow-arrow">&rarr;</span>
        <span className="flow-node">triage &amp; gate</span>
        <span className="flow-arrow">&rarr;</span>
        <span className="flow-node">route to the models with the best record</span>
        <span className="flow-arrow">&rarr;</span>
        <span className="flow-node">test every patch</span>
        <span className="flow-arrow">&rarr;</span>
        <span className="flow-node accent">keep what passes</span>
      </div>

      <span className="stage-label">How it relates to BlackBox</span>
      <div className="cmp">
        <div className="cmp-row cmp-head">
          <div>BlackBox AI</div>
          <div>Agenclave (this project)</div>
        </div>
        {CONCEPT_MAP.map((row, i) => (
          <div className="cmp-row" key={i}>
            <div className="cmp-bb">{row.bb}</div>
            <div className="cmp-ag">{row.ag}</div>
          </div>
        ))}
      </div>

      <span className="stage-label">Notes</span>
      <div className="honesty">
        The reliability numbers only come from test runs the app did itself, on ten practice bugs
        that ship with the repo. They are small samples and they move. A free-text issue has no
        repo to test against, so the Chairman judges it by reading and nothing is recorded. The
        triage classifier is TF-IDF + logistic regression; I tried MiniLM embeddings and they scored
        lower, so I didn&rsquo;t ship them.
      </div>

      <div className="result-cta">
        <a className="btn-secondary" href={REPO_URL} target="_blank" rel="noreferrer">
          View the code on GitHub &rarr;
        </a>
      </div>
    </>
  )
}
