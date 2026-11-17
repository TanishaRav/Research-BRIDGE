import Link from "next/link";

export default function HomePage() {
  return (
    <main id="main-content" className="launch-shell">
      <div className="launch-mark" aria-hidden="true">RB</div>
      <p className="eyebrow">Independent EUReCA prototype</p>
      <h1>ResearchBridge</h1>
      <p className="launch-copy">
        Transparent batch placement for limited undergraduate research opportunities.
        Every profile in this demo is synthetic.
      </p>
      <Link className="button button-primary" href="/student">
        Open synthetic demo
      </Link>
      <p className="launch-note">
        Demo role switching is not authentication. No email is sent and no university
        system is connected.
      </p>
    </main>
  );
}
