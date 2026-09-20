import { useEffect, useState } from 'react'
import './App.css'

// In dev, Vite serves the frontend on :5173 and the API runs separately on :8000.
// In production, FastAPI serves this build itself, so relative requests reach the same origin.
const API_BASE_URL = import.meta.env.DEV ? 'http://localhost:8000' : ''
const CV_ID_STORAGE_KEY = 'jobfit.cvId'

// Purely presentational: buckets the deterministic fit score into a color band
// so it's easier to scan. Does not change the score's value or meaning.
function getFitScoreLevel(score) {
  if (score >= 70) return 'high'
  if (score >= 40) return 'medium'
  return 'low'
}

// Purely presentational: the API returns the exact float (e.g. 66.66666666666666);
// this only rounds it for display, it does not change the underlying value.
function formatFitScore(score) {
  return score.toFixed(1)
}

// Purely presentational: the API returns a raw ISO timestamp; this only
// formats it for display, it does not change the underlying stored value.
function formatTimestamp(isoString) {
  return new Date(isoString).toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function App() {
  const [cvText, setCvText] = useState('')
  const [cvId, setCvId] = useState(null)
  const [isSavingCv, setIsSavingCv] = useState(false)
  const [cvError, setCvError] = useState(null)

  const [jobDescription, setJobDescription] = useState('')
  const [analysisResult, setAnalysisResult] = useState(null)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [analysisError, setAnalysisError] = useState(null)

  const [analysisHistory, setAnalysisHistory] = useState([])
  const [historyError, setHistoryError] = useState(null)
  const [isLoadingHistory, setIsLoadingHistory] = useState(false)

  const fetchAnalysisHistory = async () => {
    setIsLoadingHistory(true)
    setHistoryError(null)

    try {
      const response = await fetch(`${API_BASE_URL}/analyses`)

      if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`)
      }

      const data = await response.json()
      setAnalysisHistory(data)
    } catch (err) {
      setHistoryError('Could not load analysis history.')
    } finally {
      setIsLoadingHistory(false)
    }
  }

  useEffect(() => {
    fetchAnalysisHistory()
  }, [])

  const handleSelectHistoryItem = async (analysisId) => {
    setHistoryError(null)

    try {
      const response = await fetch(`${API_BASE_URL}/analyses/${analysisId}`)

      if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`)
      }

      const data = await response.json()
      setAnalysisResult(data)
    } catch (err) {
      setHistoryError('Could not load the selected analysis.')
    }
  }

  useEffect(() => {
    const savedCvId = localStorage.getItem(CV_ID_STORAGE_KEY)
    if (!savedCvId) {
      return
    }

    const restoreCv = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/cv/${savedCvId}`)

        if (!response.ok) {
          throw new Error(`Request failed with status ${response.status}`)
        }

        const data = await response.json()
        setCvId(data.cv_id)
        setCvText(data.cv_text)
      } catch (err) {
        localStorage.removeItem(CV_ID_STORAGE_KEY)
        setCvError('Your previously saved CV could not be found. Please paste it again.')
      }
    }

    restoreCv()
  }, [])

  const handleSaveCv = async () => {
    setIsSavingCv(true)
    setCvError(null)

    const url = cvId === null ? `${API_BASE_URL}/cv` : `${API_BASE_URL}/cv/${cvId}`
    const method = cvId === null ? 'POST' : 'PUT'

    try {
      const response = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cv_text: cvText }),
      })

      if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`)
      }

      const data = await response.json()
      setCvId(data.cv_id)
      localStorage.setItem(CV_ID_STORAGE_KEY, String(data.cv_id))
    } catch (err) {
      setCvError('Could not save CV. Please try again.')
    } finally {
      setIsSavingCv(false)
    }
  }

  const handleAnalyze = async () => {
    if (cvId === null) {
      setAnalysisError('Please save a CV before analyzing.')
      return
    }

    setIsAnalyzing(true)
    setAnalysisError(null)

    try {
      const response = await fetch(`${API_BASE_URL}/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cv_id: cvId, job_description: jobDescription }),
      })

      if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`)
      }

      const data = await response.json()
      setAnalysisResult(data)
      fetchAnalysisHistory()
    } catch (err) {
      setAnalysisError('Could not analyze job fit. Please try again.')
    } finally {
      setIsAnalyzing(false)
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>JobFit AI</h1>
        <p className="app-subtitle">AI-assisted CV-to-job-description fit analysis</p>
      </header>

      <div className="input-grid">
        <section className="section">
          <h2>CV</h2>
          <textarea
            className="text-input"
            value={cvText}
            onChange={(event) => setCvText(event.target.value)}
            placeholder="Paste your CV text here..."
            rows={10}
          />
          <div className="actions">
            <button
              type="button"
              className="button button-primary"
              onClick={handleSaveCv}
              disabled={isSavingCv || !cvText.trim()}
            >
              {isSavingCv ? 'Saving…' : 'Save CV'}
            </button>
            {cvId !== null && <span className="state-message state-message-success">Saved (ID {cvId})</span>}
          </div>
          {cvError && <p className="state-message state-message-error">{cvError}</p>}
        </section>

        <section className="section">
          <h2>Job Description</h2>
          <textarea
            className="text-input"
            value={jobDescription}
            onChange={(event) => setJobDescription(event.target.value)}
            placeholder="Paste the job description here..."
            rows={10}
          />
          <div className="actions">
            <button
              type="button"
              className="button button-primary"
              onClick={handleAnalyze}
              disabled={isAnalyzing || !jobDescription.trim() || cvId === null}
            >
              {isAnalyzing ? 'Analyzing…' : 'Analyze'}
            </button>
            {cvId === null && (
              <span className="state-message state-message-muted">Save a CV first to enable analysis</span>
            )}
          </div>
          {analysisError && <p className="state-message state-message-error">{analysisError}</p>}
        </section>
      </div>

      <section className="section">
        <h2>Analysis Result</h2>
        {!analysisResult && (
          <p className="state-message state-message-muted">The analysis result will be shown here.</p>
        )}
        {analysisResult && (
          <div className="analysis-result">
            <div className={`fit-score-card fit-score-card--${getFitScoreLevel(analysisResult.fit_score)}`}>
              <div className="fit-score-value">{formatFitScore(analysisResult.fit_score)}%</div>
              <div className="fit-score-meta">
                <p className="fit-score-label">Fit score</p>
                <p className="fit-score-caption">
                  Deterministic score based on matched requirements — not a probability or hiring
                  recommendation.
                </p>
              </div>
            </div>

            <div className="source-grid">
              <div className="analysis-source">
                <p className="analysis-source-label">CV used for this analysis</p>
                <pre className="analysis-source-text">{analysisResult.cv_text_snapshot}</pre>
              </div>
              <div className="analysis-source">
                <p className="analysis-source-label">Job description used for this analysis</p>
                <pre className="analysis-source-text">{analysisResult.job_description}</pre>
              </div>
            </div>

            <ul className="match-list">
              {analysisResult.matches.map((match) => (
                <li key={match.requirement.name} className="match-item">
                  <div className="match-header">
                    <p className="match-name">
                      {match.requirement.name}
                      <span className="importance-tag">{match.requirement.importance}</span>
                    </p>
                    <span className={`status-badge status-badge--${match.status}`}>
                      {match.status.replace('_', ' ')}
                    </span>
                  </div>
                  <div className="match-evidence-block">
                    <p className="match-evidence-label">Evidence</p>
                    {match.cv_evidence ? (
                      <blockquote className="match-evidence">{match.cv_evidence}</blockquote>
                    ) : (
                      <p className="match-evidence match-evidence--empty">
                        No supporting evidence found in the CV.
                      </p>
                    )}
                  </div>
                  <p className="match-explanation">{match.explanation}</p>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <section className="section">
        <h2>Analysis History</h2>
        {isLoadingHistory && <p className="state-message state-message-muted">Loading history…</p>}
        {historyError && <p className="state-message state-message-error">{historyError}</p>}
        {!isLoadingHistory && analysisHistory.length === 0 && (
          <p className="state-message state-message-muted">No analyses yet.</p>
        )}
        {analysisHistory.length > 0 && (
          <ul className="history-list">
            {analysisHistory.map((item) => (
              <li key={item.id} className="history-item">
                <button
                  type="button"
                  className="history-item-button"
                  onClick={() => handleSelectHistoryItem(item.id)}
                >
                  <span className="history-job-description">#{item.id} — {item.job_description}</span>
                  <span className="history-meta">
                    <span className="history-score">{formatFitScore(item.fit_score)}%</span>
                    <span className="history-date">{formatTimestamp(item.created_at)}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}

export default App
