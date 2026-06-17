# ⚽ Vorsorge-Backtest für Profi-Fußballer

Streamlit-Tool zur Simulation der Altersvorsorge eines Profi-Fußballers
("Sommerprämien"-Konzept) auf Basis historischer Total-Return-Daten in EUR.

Modelliert wird ein vollständiger Lebenszyklus:
- **Ansparphase**: monatliche Einzahlungen während der aktiven Karriere
- **Entsparphase**: monatliche Entnahmen nach Karriereende, inflationsindexiert

Methodik: **Historischer Rolling-Backtest** über alle möglichen
Startmonate seit 1970.

---

## 📊 Features

- **4 Anlageklassen** frei kombinierbar: MSCI World, REXP (Deutschland),
  Gold, Cash
- **Wählbare Parameter** für Karriereprofil, Sparrate, Entnahmehöhe,
  Inflationsindexierung, TER
- **Fan-Chart** der Equitykurve mit P10 / P25 / P50 / P75 / P90
- **Kennzahlen**: Erfolgsquote, Endvermögen (Median/P10/P90),
  Max Drawdown, CAGR, Volatilität
- **Safe Withdrawal Rate** per Bisection-Suche
- **Histogramme** für Endvermögen und Max Drawdown
- **CSV-Export** aller Szenario-Ergebnisse
- **Eigene Excel** hochladbar (gleiches Schema)

---

## 🚀 Quick Start (lokal)

```bash
git clone <repo-url>
cd fussballer-vorsorge-backtest
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Öffnet sich automatisch im Browser unter http://localhost:8501.

---

## ☁️ Deployment auf Streamlit Community Cloud (kostenlos)

1. Repo auf GitHub pushen (öffentlich oder privat).
2. Auf https://share.streamlit.io einloggen mit GitHub.
3. **New app** → Repo / Branch / `app.py` auswählen → **Deploy**.
4. Nach ~2 Minuten ist die App unter `https://<user>-<repo>.streamlit.app` erreichbar.

Die `requirements.txt` und `.streamlit/config.toml` sind bereits passend vorkonfiguriert.

---

## 📁 Projektstruktur

```
fussballer-vorsorge-backtest/
├── app.py                       # Streamlit-Hauptapp
├── backtest/
│   ├── __init__.py
│   ├── data_loader.py           # Excel-Einlesen, Returns berechnen
│   ├── simulation.py            # Anspar-/Entsparlogik
│   └── metrics.py               # Aggregierte Kennzahlen, SWR
├── data/
│   └── Daten_Verrentung_EUR.xlsx
├── .streamlit/config.toml       # Theme & Limits
├── requirements.txt
├── .gitignore
└── README.md
```

---

## 📐 Methodik im Detail

### Datenquelle
Monatliche Total-Return-Indizes in EUR aus `Daten_Verrentung_EUR.xlsx`.
Spaltenmapping:

| Spalte (Excel)   | Anlageklasse           | Verfügbar ab |
|------------------|------------------------|--------------|
| `NDDUWI Index`   | MSCI World (Net TR)    | 1970         |
| `REXP Index`     | Deutscher Rentenindex  | 1970         |
| `Gold`           | Gold (EUR)             | 1926         |
| `Inflation DE`   | Verbraucherpreisindex  | 1948         |

Effektiver Backtest-Startzeitpunkt: **Februar 1970**.
Cash wird mit konstantem nominalen Jahreszins simuliert (Default 2 %).

### Ansparphase
- Monatliche Einzahlung = `Sparrate p.a. / 12`
- Cashflow nach der Marktbewegung des Monats addiert
- Optional inflationsindexiert (kumulierte Monats-CPI-Faktoren)

### Entsparphase
- Monatliche Entnahme zum Festbetrag (Brutto)
- Optional inflationsindexiert (gemäß bisheriger kumulativer Inflation)
- Wird der gewünschte Betrag nicht mehr gedeckt: Restportfolio wird entnommen,
  Szenario gilt als "erschöpft"

### Rebalancing
Implizit **monatlich** auf Zielgewichte – das Portfolio wird nicht als
einzelne Asset-Buckets geführt, sondern als gewichteter Composite-Return
auf das jeweils aktuelle Gesamtvermögen.

### Kosten
TER (Default 0,5 % p.a.) wird **monatlich anteilig geometrisch** vom
Portfoliowert abgezogen (`(1 - TER)^(1/12) - 1`).

### Steuern
In dieser Version **nicht** modelliert (brutto-Ansatz). Das spezielle
Steuerregime der Sommerprämie würde eine eigene Modellierung erfordern.

### Rolling-Backtest
Für **jeden** Monat im Datensatz, ab dem ein vollständiger Lebenszyklus
(Karrierestart bis Endalter) in die Historie passt, wird ein
deterministischer Lauf gerechnet. Ergebnis: 1 Equitykurve + Kennzahlen
pro Startmonat.

**Aussagekraftsgrenze**: bei einem Lebenszyklus von z.B. 60 Jahren passen
in 55 Jahre Historie nur wenige Startpunkte. Die App warnt, wenn weniger
als 10 Rolling-Szenarien möglich sind.

### Safe Withdrawal Rate (SWR)
Bisection-Suche nach dem höchsten monatlichen Entnahmebetrag, bei dem
≥95 % der Rolling-Szenarien NICHT erschöpfen. Default-Suchbereich:
500–50.000 €/Monat, Genauigkeit 50 €.

---

## 🛠️ Erweiterungsideen

- **Monte-Carlo-Modus** zusätzlich zum historischen Backtest
- **Steuern**: Abgeltungsteuer (mit Teilfreistellung) oder spezifisches
  Sommerprämien-Regime
- **Dynamische Sparrate** abhängig vom Karriereverlauf (Peak-Years 25–30)
- **Glidepath**: Allokation altersabhängig (Aktienquote runter im Alter)
- **Variable Entnahme-Regeln**: Guyton-Klinger, CAPE-basiert, % vom Portfolio
- **Mehrere Vergleichsallokationen** parallel im Fan-Chart

---

## ⚠️ Disclaimer

Diese Simulation dient ausschließlich Anschauungs- und Forschungszwecken.
Sie stellt **keine Anlageberatung** dar. Vergangene Wertentwicklung ist
kein verlässlicher Indikator für zukünftige Ergebnisse.
