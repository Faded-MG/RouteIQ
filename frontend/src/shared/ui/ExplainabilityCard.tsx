import "./ExplainabilityCard.css";

export function ExplainabilityCard() {
  return (
    <div className="explainability-card">
      <div className="explainability-card__header">
        <svg
          className="explainability-card__icon"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
          />
        </svg>
        <span>Assessment Engine Assumptions &amp; Method</span>
      </div>

      <ul className="explainability-card__list">
        <li className="explainability-card__item">
          <span className="explainability-card__bullet">&bull;</span>
          <span>
            <strong className="explainability-card__strong">Vehicle Constraint:</strong> Maximum range of 500 miles at 10 MPG (50.0-gallon tank). Start tank empty (0 gal).
          </span>
        </li>
        <li className="explainability-card__item">
          <span className="explainability-card__bullet">&bull;</span>
          <span>
            <strong className="explainability-card__strong">Pricing Data:</strong> 6,626 US fuel stations loaded from Spotter CSV with per-station median diesel prices.
          </span>
        </li>
        <li className="explainability-card__item">
          <span className="explainability-card__bullet">&bull;</span>
          <span>
            <strong className="explainability-card__strong">Exact Dynamic Programming:</strong> Evaluates discrete 0.01-gal states to strictly minimize total dollars spent. Detours priced into selection.
          </span>
        </li>
        <li className="explainability-card__item">
          <span className="explainability-card__bullet">&bull;</span>
          <span>
            <strong className="explainability-card__strong">Independent Validator:</strong> Every plan is verified by continuous float re-simulation to mathematically prove the vehicle never runs dry.
          </span>
        </li>
      </ul>
    </div>
  );
}
