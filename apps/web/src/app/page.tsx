export default function HomePage() {
  return (
    <>
      <h1>Pantheon MVP Web Shell</h1>
      <p className="muted">
        Week 1 scaffold for frontend bootstrap. Auth and room workflows are added in subsequent tasks.
      </p>

      <div className="card-grid">
        <section className="card">
          <h3>Auth Placeholder</h3>
          <p className="muted">Magic-link login and callback routes are scaffolded.</p>
        </section>
        <section className="card">
          <h3>Rooms Placeholder</h3>
          <p className="muted">Room list/create screens will be added after backend auth wiring.</p>
        </section>
        <section className="card">
          <h3>Chat Placeholder</h3>
          <p className="muted">Streaming chat timeline integration planned in Week 1-2 tasks.</p>
        </section>
      </div>
    </>
  );
}

