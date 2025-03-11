#%%
import pandas as pd
import requests
import plotly.express as px
import numpy as np
import dash
from dash import dcc
from dash import html
import dash_bootstrap_components as dbc
from flask import Flask
from dash.dependencies import Input, Output
import os

#%%
# Google Drive Datei-IDs
file_id1 = "1hUkTfreEEvXXh-ka1C0RkHLcUVngQnLU"

# URLs für den Download
url1 = f"https://drive.google.com/uc?id={file_id1}"

# Dateien herunterladen und speichern
r1 = requests.get(url1)

with open("data_all.xlsx", "wb") as f:
    f.write(r1.content)

#%% Data Management

# Daten in Pandas einlesen
data_all = pd.read_excel("data_all.xlsx")

# Transform Data to Long Format (Includes Erststimme and Zweitstimme)
data_all_long = (
    data_all
    .melt(id_vars=['wahljahr', 'gebiet'],
          value_vars=[col for col in data_all.columns if 'percent' in col],  # Only percent columns
          var_name='Partei_Stimme', value_name='Stimmen')
    .assign(
        Stimme=lambda df: df['Partei_Stimme'].str.extract(r'^(erst|zweit)')[0],  # Extract vote type (erst or zweit)
        Partei=lambda df: df['Partei_Stimme'].str.replace(r'^(erst_|zweit_)', '', regex=True)  # Extract party
    )
)

#%% Customization

# Custom color palette for parties
party_colors = {
    'AFD': '#0489DB',
    'CDU': '#000000',
    'FDP': '#FFEF00',
    'GRÜNE': '#1AA037',
    'DIE LINKE': '#be3075',
    'SPD': '#e3000f'
}

# Define display names for parties
party_display_names = {
    "afd_percent": "AFD",
    "cdu_percent": "CDU",
    "fdp_percent": "FDP",
    "gruene_percent": "GRÜNE",
    "linke_percent": "DIE LINKE",
    "spd_percent": "SPD"
}

# Custom styles for the checklist
CHECKLIST_STYLE = {"margin-bottom": "10px", "font-weight": "bold"}
CARD_STYLE = {"padding": "10px", "border-radius": "5px", "background-color": "#f8f9fa"}

#%%

server = Flask(__name__)  # Flask app
app = dash.Dash(__name__, server=server, external_stylesheets=[dbc.themes.BOOTSTRAP])  # Dash app tied to Flask server

# 2. Setup the application - This should happen before `run_server()`
# You can add any error handlers here, for example:
@server.errorhandler(404)
def page_not_found(error):
    return "Page not found", 404

# Layout of the app with filters and graph
app.layout = dbc.Container([
    html.H4('📊 Wahlverhalten in Münster (Prozentual)', className="mt-3 mb-4 text-center"),
    dcc.Graph(id="graph", style={"margin-bottom": "20px"}),

    dbc.Row([
        dbc.Col(dbc.Card([
            html.Label("🗳️ Wähle Stimmenart:", style=CHECKLIST_STYLE),
            dbc.Checklist(
                id="stimme-checklist",
                options=[{"label": "Erststimme", "value": "erst"}, {"label": "Zweitstimme", "value": "zweit"}],
                value=["zweit"],
                inline=True,
                switch=True
            )
        ], style=CARD_STYLE), width=3),

        dbc.Col(dbc.Card([
            html.Label("📍 Wähle Region(en):", style=CHECKLIST_STYLE),
            dbc.Checklist(
                id="gebiet-checklist",
                options=[{"label": region, "value": region} for region in sorted(data_all_long['gebiet'].unique())],
                value=["Gesamt"],
                inline=True
            )
        ], style=CARD_STYLE), width=3),

        dbc.Col(dbc.Card([
            html.Label("🏛️ Wähle Partei(en):", style=CHECKLIST_STYLE),
            dbc.Checklist(
                id="party-checklist",
                options=[{"label": party_display_names.get(party, party), "value": party} for party in sorted(data_all_long['Partei'].unique())],
                value=sorted(data_all_long['Partei'].unique()),
                inline=True
            )
        ], style=CARD_STYLE), width=3),

        dbc.Col(dbc.Card([
            html.Label("📅 Wähle Jahr(e):", style=CHECKLIST_STYLE),
            dbc.Checklist(
                id='year-checklist',
                options=[{'label': str(year), 'value': year} for year in sorted(data_all_long['wahljahr'].unique())],
                value=sorted(data_all_long['wahljahr'].unique()),
                inline=True
            )
        ], style=CARD_STYLE), width=3),
    ], className="mb-4")
])

# Callback function to update the graph based on selected filters
@app.callback(
    Output('graph', 'figure'),
    [Input('stimme-checklist', 'value'),
     Input('gebiet-checklist', 'value'),
     Input('party-checklist', 'value'),
     Input('year-checklist', 'value')]
)
def update_chart(selected_stimme, selected_regions, selected_parties, selected_years):
    filtered_df = data_all_long.query(
        "Stimme in @selected_stimme and gebiet in @selected_regions and Partei in @selected_parties and wahljahr in @selected_years"
    )

    if filtered_df.empty:
        return px.line(title="Keine Daten für die ausgewählten Filter verfügbar")

    filtered_df = filtered_df.copy()
    filtered_df['Partei_Display'] = filtered_df['Partei'].map(party_display_names).fillna(filtered_df['Partei'])
    filtered_df['Partei_Stimme_Gebiet'] = filtered_df['Partei_Display'] + " (" + filtered_df['Stimme'] + ") - " + filtered_df['gebiet']

    fig = px.line(
        filtered_df,
        x='wahljahr',
        y='Stimmen',
        color='Partei_Stimme_Gebiet',
        markers=True,
        color_discrete_map={party: party_colors.get(party.split(" (")[0], "#999999") for party in filtered_df['Partei_Stimme_Gebiet'].unique()},
    )

    for trace in fig.data:
        stimme_typ = trace.name.split(" (")[1].split(")")[0]
        trace.line.dash = "solid" if stimme_typ == "zweit" else "dashdot"

    y_min = max(0, filtered_df['Stimmen'].min() - 5)
    y_max = min(100, filtered_df['Stimmen'].max() + 5)
    fig.update_layout(yaxis=dict(range=[y_min, y_max]))

    last_points = filtered_df.loc[filtered_df.groupby(['Partei_Stimme_Gebiet'])['wahljahr'].idxmax()]

    for _, row in last_points.iterrows():
        fig.add_annotation(
            x=row['wahljahr'],
            y=row['Stimmen'],
            text=row['gebiet'],
            showarrow=False,
            yshift=10
        )

    fig.update_layout(
        title="Wahlverhalten in Münster (Prozentual)",
        xaxis_title="Jahr",
        yaxis_title="Stimmenanteil (%)",
        xaxis=dict(tickmode='array', tickvals=sorted(data_all_long['wahljahr'].unique())),
        template="plotly_white"
    )

    return fig


#%%
# If you are running locally, you can still use the following:
# if __name__ == "__main__":
#     print("Starting Dash app...")
#     port = int(os.environ.get("PORT", 8080))  # Get Render's PORT
#     app.run_server(debug=False, host="0.0.0.0", port=port)  # 0.0.0.0 makes it accessible from the internet

# Gunicorn will now run this `server` object
server = app.server  # This is the WSGI app Gunicorn expects