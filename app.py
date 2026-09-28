import html
import json
import re
import uuid
from datetime import date, datetime, timedelta

import streamlit as st

st.set_page_config(page_title="ESN Artistique", page_icon="🎨", layout="wide")

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.5rem; padding-bottom: 4rem;}
    .hero {padding: 26px; border-radius: 18px; color: white;
           background: linear-gradient(135deg,#18354D,#25647A); margin-bottom: 20px;}
    .card {padding: 16px; border: 1px solid #DDE6EA; border-radius: 14px;
           background: white; margin-bottom: 12px;}
    .score {color:#0B7E76; font-size:24px; font-weight:800;}
    .muted {color:#65727A; font-size:14px;}
    div[data-testid="stMetric"] {border:1px solid #DDE6EA; padding:14px;
                                 border-radius:12px; background:white;}
    .stButton > button {background:#18A99A; color:white; border:none; font-weight:700;}
    </style>
    """,
    unsafe_allow_html=True,
)

PROFESSIONS = [
    "Photographe",
    "Vidéaste",
    "Monteur vidéo",
    "Pilote de drone",
    "Graphiste",
    "Motion designer",
    "Directeur artistique",
    "Community manager",
    "Maquilleur / Maquilleuse",
    "Styliste",
    "Illustrateur / Illustratrice",
    "Retoucheur / Retoucheuse",
    "Sound designer",
    "Ingénieur du son",
    "Rédacteur / Rédactrice",
]

SUPPORTS = {
    "Usage interne": 0.35,
    "Réseaux sociaux organiques": 0.70,
    "Site institutionnel": 0.70,
    "Presse éditoriale": 1.00,
    "Édition commerciale": 1.25,
    "Affichage promotionnel": 1.10,
    "Campagne publicitaire": 1.80,
    "Packaging / merchandising": 1.60,
}

DIFFUSIONS = {
    "Moins de 1 000 exemplaires / vues": 0.60,
    "1 000 à 10 000": 0.85,
    "10 001 à 100 000": 1.10,
    "100 001 à 1 000 000": 1.45,
    "Plus de 1 000 000": 1.90,
}

TERRITOIRES = {
    "Local / régional": 0.70,
    "France": 1.00,
    "Europe": 1.30,
    "Monde": 1.65,
}

DUREES = {
    "Opération ponctuelle, 3 mois maximum": 0.60,
    "Jusqu'à 1 an": 1.00,
    "Jusqu'à 3 ans": 1.35,
    "Plus de 3 ans": 1.75,
}

EXCLUSIVITES = {
    "Aucune exclusivité": 1.00,
    "Exclusivité limitée à un secteur": 1.25,
    "Exclusivité territoriale": 1.45,
    "Exclusivité totale": 1.90,
}

for key, default in {
    "talents": [],
    "briefs": [],
    "quotes": [],
    "selected_quote": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


def euro(value):
    return f"{value:,.2f} €".replace(",", " ")


def as_list(value):
    if isinstance(value, list):
        return value
    if not value:
        return []
    return [item.strip() for item in str(value).split(",") if item.strip()]


def tokens(value):
    return {
        item
        for item in re.split(r"[^a-zA-ZÀ-ÿ0-9]+", (value or "").lower())
        if len(item) > 1
    }


def calculate_match(talent, brief):
    talent_professions = set(as_list(talent.get("professions", talent.get("profession", []))))
    brief_professions = set(as_list(brief.get("professions", [])))
    profession_overlap = talent_professions.intersection(brief_professions)

    if not profession_overlap:
        return None

    score = 60
    reasons = ["Profession compatible : " + ", ".join(sorted(profession_overlap)) + "."]
    gaps = []

    wanted_styles = tokens(brief.get("styles", ""))
    talent_styles = tokens(talent.get("styles", ""))
    style_overlap = wanted_styles.intersection(talent_styles)

    if wanted_styles:
        score += round(20 * len(style_overlap) / len(wanted_styles))
        if style_overlap:
            reasons.append("Univers compatible : " + ", ".join(sorted(style_overlap)) + ".")
        else:
            gaps.append("Adéquation artistique à challenger.")
    else:
        score += 5
        reasons.append("Direction artistique encore ouverte.")

    brief_location = brief.get("location", "").strip().lower()
    talent_location = talent.get("location", "").strip().lower()
    if brief_location and talent_location:
        if brief_location in talent_location or talent_location in brief_location:
            score += 10
            reasons.append("Zone géographique compatible.")
        else:
            gaps.append("Déplacement ou frais à confirmer.")

    if talent.get("availability", "").lower() != "indisponible":
        score += 5
        reasons.append("Disponibilité potentielle.")
    else:
        gaps.append("Talent déclaré indisponible.")

    return {
        **talent,
        "match_score": min(score, 100),
        "match_reasons": reasons,
        "match_gaps": gaps,
    }


def generate_shortlist(brief, limit=5):
    results = []
    for talent in st.session_state.talents:
        result = calculate_match(talent, brief)
        if result is not None:
            results.append(result)
    return sorted(results, key=lambda item: item["match_score"], reverse=True)[:limit]


def calculate_price(
    talent,
    preparation_hours,
    production_days,
    postproduction_hours,
    hourly_rate,
    day_rate,
    base_rights,
    support,
    diffusion,
    territory,
    duration,
    exclusivity,
    urgency_percent,
    technical_fees,
    travel_fees,
    options,
    discount_percent,
):
    hourly_rate = hourly_rate or float(talent.get("hourly_rate", 0) or 0)
    day_rate = day_rate or float(talent.get("day_rate", 0) or 0)
    base_rights = base_rights or float(talent.get("base_rights", 0) or 0)

    preparation = preparation_hours * hourly_rate
    production = production_days * day_rate
    postproduction = postproduction_hours * hourly_rate
    production_subtotal = preparation + production + postproduction
    urgency = production_subtotal * urgency_percent / 100

    rights_multiplier = (
        SUPPORTS[support]
        * DIFFUSIONS[diffusion]
        * TERRITOIRES[territory]
        * DUREES[duration]
        * EXCLUSIVITES[exclusivity]
    )
    rights = base_rights * rights_multiplier

    subtotal = (
        production_subtotal
        + urgency
        + rights
        + technical_fees
        + travel_fees
        + options
    )
    discount = subtotal * discount_percent / 100
    total_ht = max(0, subtotal - discount)

    return {
        "preparation": preparation,
        "production": production,
        "postproduction": postproduction,
        "production_subtotal": production_subtotal,
        "urgency": urgency,
        "rights": rights,
        "rights_multiplier": rights_multiplier,
        "technical_fees": technical_fees,
        "travel_fees": travel_fees,
        "options": options,
        "discount": discount,
        "total_ht": total_ht,
    }


def create_quote_html(quote):
    def clean(value):
        return html.escape(str(value or "")).replace("\n", "<br>")

    rows = []
    pricing = quote["pricing"]
    lines = [
        ("Préparation et cadrage", "preparation"),
        ("Production / création", "production"),
        ("Postproduction", "postproduction"),
        ("Majoration urgence", "urgency"),
        ("Droits d'exploitation", "rights"),
        ("Frais techniques", "technical_fees"),
        ("Déplacements", "travel_fees"),
        ("Options complémentaires", "options"),
    ]
    for label, key in lines:
        if pricing[key]:
            rows.append(f"<tr><td>{label}</td><td>{euro(pricing[key])}</td></tr>")
    if pricing["discount"]:
        rows.append(f"<tr><td>Remise commerciale</td><td>- {euro(pricing['discount'])}</td></tr>")

    return f"""<!doctype html>
<html lang='fr'>
<head>
<meta charset='utf-8'>
<title>{clean(quote['number'])}</title>
<style>
body{{font-family:Arial,sans-serif;color:#263441;margin:40px;line-height:1.4}}
h1{{color:#18354D;text-align:center}} .grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}
.box{{border:1px solid #CBD5DA;padding:16px}} table{{width:100%;border-collapse:collapse;margin-top:18px}}
th{{background:#18354D;color:white}} th,td{{border:1px solid #CBD5DA;padding:10px;text-align:left}}
td:last-child{{text-align:right}} .total{{background:#EAF6F4;font-weight:bold;font-size:18px}}
.small{{font-size:11px;color:#65727A}} @media print{{button{{display:none}} body{{margin:15mm}}}}
</style>
</head>
<body>
<h1>DEVIS</h1>
<div class='grid'>
<div class='box'><b>Émetteur</b><br>{clean(quote['issuer'])}<br>{clean(quote['issuer_address'])}<br>{clean(quote['issuer_email'])}</div>
<div class='box'><b>Devis n°</b> {clean(quote['number'])}<br><b>Date</b> {clean(quote['date'])}<br><b>Valable jusqu'au</b> {clean(quote['valid_until'])}</div>
<div class='box'><b>Client</b><br>{clean(quote['client'])}<br>{clean(quote['client_address'])}<br>{clean(quote['client_email'])}</div>
<div class='box'><b>Projet</b><br>{clean(quote['project'])}<br><b>Talent</b><br>{clean(quote['talent'])}</div>
</div>
<table><tr><th>Désignation</th><th>Montant HT</th></tr>{''.join(rows)}<tr class='total'><td>TOTAL HT</td><td>{euro(pricing['total_ht'])}</td></tr></table>
<h2>Périmètre des droits d'exploitation</h2>
<table>
<tr><td><b>Support</b></td><td>{clean(quote['support'])}</td></tr>
<tr><td><b>Diffusion</b></td><td>{clean(quote['diffusion'])}</td></tr>
<tr><td><b>Territoire</b></td><td>{clean(quote['territory'])}</td></tr>
<tr><td><b>Durée</b></td><td>{clean(quote['duration'])}</td></tr>
<tr><td><b>Exclusivité</b></td><td>{clean(quote['exclusivity'])}</td></tr>
</table>
<p><b>Livrables :</b><br>{clean(quote['deliverables'])}</p>
<p><b>Conditions :</b><br>{clean(quote['conditions'])}</p>
<p class='small'>Le prix des droits est une estimation commerciale interne. Les droits effectivement cédés doivent être décrits précisément et validés dans le devis ou le contrat. Ce document ne constitue pas un avis juridique ni un barème officiel.</p>
<p><b>Pour obtenir un PDF :</b> ouvre ce fichier dans ton navigateur puis utilise Imprimer → Enregistrer au format PDF.</p>
</body></html>"""


st.markdown(
    """<div class='hero'><h1>🎨 ESN Artistique</h1>
    <p>Vivier, briefs, matching métier strict, calcul des droits et devis.</p></div>""",
    unsafe_allow_html=True,
)

tabs = st.tabs([
    "📊 Tableau de bord",
    "👤 Talents",
    "📝 Briefs",
    "🎯 Matching & tarif",
    "📄 Devis",
    "💾 Sauvegarde",
])

with tabs[0]:
    c1, c2, c3 = st.columns(3)
    c1.metric("Talents", len(st.session_state.talents))
    c2.metric("Briefs", len(st.session_state.briefs))
    c3.metric("Devis", len(st.session_state.quotes))
    st.info("Sans profession commune entre le talent et le brief, le profil est exclu du matching.")
    st.warning("Les coefficients de droits sont des règles internes de simulation, pas des barèmes officiels.")

with tabs[1]:
    st.subheader("Ajouter un talent")
    with st.form("talent_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            name = st.text_input("Nom *")
            professions = st.multiselect("Professions *", PROFESSIONS)
            styles = st.text_input("Univers artistiques")
            skills = st.text_area("Compétences")
            location = st.text_input("Zone géographique")
        with c2:
            day_rate = st.number_input("Tarif de production par jour HT", min_value=0.0, step=50.0)
            hourly_rate = st.number_input("Tarif préparation / postproduction par heure HT", min_value=0.0, step=10.0)
            base_rights = st.number_input("Base de droits d'exploitation HT", min_value=0.0, step=50.0)
            availability = st.selectbox("Disponibilité", ["Disponible", "À confirmer", "Partielle", "Indisponible"])
            portfolio = st.text_input("Lien portfolio")
        notes = st.text_area("Notes internes")
        if st.form_submit_button("Ajouter le talent"):
            if not name or not professions:
                st.error("Le nom et au moins une profession sont obligatoires.")
            else:
                st.session_state.talents.append({
                    "id": str(uuid.uuid4()), "name": name, "professions": professions,
                    "styles": styles, "skills": skills, "location": location,
                    "day_rate": day_rate, "hourly_rate": hourly_rate,
                    "base_rights": base_rights, "availability": availability,
                    "portfolio": portfolio, "notes": notes,
                })
                st.success("Talent ajouté.")

    for index, talent in enumerate(st.session_state.talents):
        with st.expander(f"{talent['name']} · {', '.join(as_list(talent.get('professions', talent.get('profession', []))))}"):
            st.write("**Professions :**", ", ".join(as_list(talent.get("professions", talent.get("profession", [])))))
            st.write("**Tarif jour :**", euro(float(talent.get("day_rate", talent.get("rate", 0)) or 0)))
            st.write("**Base de droits :**", euro(float(talent.get("base_rights", 0) or 0)))
            if talent.get("portfolio"):
                st.markdown(f"[Voir le portfolio]({talent['portfolio']})")
            if st.button("Supprimer ce talent", key=f"delete_talent_{index}"):
                st.session_state.talents.pop(index)
                st.rerun()

with tabs[2]:
    st.subheader("Créer un brief")
    with st.form("brief_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            client = st.text_input("Client *")
            project = st.text_input("Projet *")
            professions = st.multiselect("Professions recherchées *", PROFESSIONS)
            styles = st.text_input("Univers souhaités")
            location = st.text_input("Lieu / zone")
        with c2:
            contact = st.text_input("Contact client")
            email = st.text_input("Email client")
            address = st.text_area("Adresse client")
            budget = st.number_input("Budget global indicatif HT", min_value=0.0, step=100.0)
            deadline = st.text_input("Échéance")
        deliverables = st.text_area("Livrables attendus")
        notes = st.text_area("Notes")
        if st.form_submit_button("Enregistrer le brief"):
            if not client or not project or not professions:
                st.error("Le client, le projet et au moins une profession sont obligatoires.")
            else:
                st.session_state.briefs.append({
                    "id": str(uuid.uuid4()), "client": client, "project": project,
                    "professions": professions, "styles": styles, "location": location,
                    "contact": contact, "email": email, "address": address,
                    "budget": budget, "deadline": deadline,
                    "deliverables": deliverables, "notes": notes,
                })
                st.success("Brief enregistré.")

    for index, brief in enumerate(st.session_state.briefs):
        with st.expander(f"{brief['client']} · {brief['project']}"):
            st.write("**Professions :**", ", ".join(as_list(brief.get("professions", []))))
            st.write("**Budget :**", euro(float(brief.get("budget", 0) or 0)))
            if st.button("Supprimer ce brief", key=f"delete_brief_{index}"):
                st.session_state.briefs.pop(index)
                st.rerun()

with tabs[3]:
    st.subheader("Matching puis calcul du tarif")
    if not st.session_state.talents or not st.session_state.briefs:
        st.info("Ajoute au moins un talent et un brief.")
    else:
        brief_map = {f"{b['client']} · {b['project']}": b for b in st.session_state.briefs}
        brief_label = st.selectbox("Brief", list(brief_map.keys()))
        brief = brief_map[brief_label]
        matches = generate_shortlist(brief, 5)

        if not matches:
            st.error("Aucun talent ne possède l'une des professions demandées. Aucun profil hors métier n'est proposé.")
        else:
            talent_map = {}
            for position, talent in enumerate(matches, 1):
                professions_label = ", ".join(as_list(talent.get("professions", talent.get("profession", []))))
                label = f"{position}. {talent['name']} · {professions_label} · {talent['match_score']}/100"
                talent_map[label] = talent
                st.markdown(
                    f"<div class='card'><div class='score'>{label}</div>"
                    f"<div class='muted'>{' | '.join(talent['match_reasons'])}</div></div>",
                    unsafe_allow_html=True,
                )

            selected_label = st.selectbox("Talent retenu", list(talent_map.keys()))
            talent = talent_map[selected_label]

            st.markdown("### 1. Production")
            c1, c2, c3 = st.columns(3)
            preparation_hours = c1.number_input("Heures de préparation", min_value=0.0, value=2.0, step=0.5)
            production_days = c1.number_input("Jours de production", min_value=0.0, value=1.0, step=0.5)
            postproduction_hours = c2.number_input("Heures de postproduction", min_value=0.0, value=3.0, step=0.5)
            hourly_rate = c2.number_input("Tarif horaire HT", min_value=0.0, value=float(talent.get("hourly_rate", 0) or 0), step=10.0)
            day_rate = c3.number_input("Tarif jour HT", min_value=0.0, value=float(talent.get("day_rate", talent.get("rate", 0)) or 0), step=50.0)
            urgency_percent = c3.number_input("Majoration urgence (%)", min_value=0.0, max_value=200.0, step=5.0)

            st.markdown("### 2. Droits d'exploitation")
            c1, c2 = st.columns(2)
            base_rights = c1.number_input("Base de droits HT", min_value=0.0, value=float(talent.get("base_rights", 0) or 0), step=50.0)
            support = c1.selectbox("Support / usage", list(SUPPORTS.keys()))
            diffusion = c1.selectbox("Nombre d'usages, exemplaires ou vues", list(DIFFUSIONS.keys()))
            territory = c2.selectbox("Territoire", list(TERRITOIRES.keys()))
            duration = c2.selectbox("Durée", list(DUREES.keys()))
            exclusivity = c2.selectbox("Exclusivité", list(EXCLUSIVITES.keys()))

            st.markdown("### 3. Frais et ajustements")
            c1, c2, c3, c4 = st.columns(4)
            technical_fees = c1.number_input("Frais techniques HT", min_value=0.0, step=50.0)
            travel_fees = c2.number_input("Déplacements HT", min_value=0.0, step=50.0)
            options = c3.number_input("Options HT", min_value=0.0, step=50.0)
            discount_percent = c4.number_input("Remise (%)", min_value=0.0, max_value=100.0, step=1.0)

            pricing = calculate_price(
                talent, preparation_hours, production_days, postproduction_hours,
                hourly_rate, day_rate, base_rights, support, diffusion, territory,
                duration, exclusivity, urgency_percent, technical_fees,
                travel_fees, options, discount_percent,
            )

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Production", euro(pricing["production_subtotal"]))
            m2.metric("Droits", euro(pricing["rights"]))
            m3.metric("Coefficient droits", f"× {pricing['rights_multiplier']:.2f}")
            m4.metric("Total HT", euro(pricing["total_ht"]))

            if brief.get("budget", 0):
                gap = float(brief["budget"]) - pricing["total_ht"]
                if gap >= 0:
                    st.success(f"Simulation sous le budget de {euro(gap)}.")
                else:
                    st.error(f"Simulation au-dessus du budget de {euro(abs(gap))}.")

            if st.button("Préparer le devis avec ce tarif"):
                st.session_state.selected_quote = {
                    "brief": brief, "talent": talent, "pricing": pricing,
                    "support": support, "diffusion": diffusion,
                    "territory": territory, "duration": duration,
                    "exclusivity": exclusivity,
                }
                st.success("Simulation transférée dans l'onglet Devis.")

with tabs[4]:
    st.subheader("Créer le devis")
    prepared = st.session_state.selected_quote
    if not prepared:
        st.info("Effectue d'abord un matching et prépare le devis.")
    else:
        brief = prepared["brief"]
        talent = prepared["talent"]
        pricing = prepared["pricing"]

        with st.form("quote_form"):
            c1, c2 = st.columns(2)
            with c1:
                issuer = st.text_input("Nom / société émettrice *")
                issuer_address = st.text_area("Adresse émetteur")
                issuer_email = st.text_input("Email émetteur")
                number = st.text_input("Numéro du devis", value=f"DEV-{datetime.now():%Y%m%d}-{len(st.session_state.quotes)+1:03d}")
            with c2:
                client = st.text_input("Client", value=brief.get("client", ""))
                client_address = st.text_area("Adresse client", value=brief.get("address", ""))
                client_email = st.text_input("Email client", value=brief.get("email", ""))
                quote_date = st.date_input("Date", value=date.today())
                valid_until = st.date_input("Valable jusqu'au", value=date.today() + timedelta(days=30))

            project = st.text_input("Projet", value=brief.get("project", ""))
            deliverables = st.text_area("Livrables", value=brief.get("deliverables", ""))
            conditions = st.text_area(
                "Conditions",
                value="Acompte et calendrier à préciser. Toute exploitation non décrite fera l'objet d'un accord complémentaire.",
            )
            st.write("**Talent :**", talent["name"], " | **Total HT :**", euro(pricing["total_ht"]))

            if st.form_submit_button("Générer le devis"):
                if not issuer:
                    st.error("Le nom de l'émetteur est obligatoire.")
                else:
                    quote = {
                        "id": str(uuid.uuid4()), "issuer": issuer,
                        "issuer_address": issuer_address, "issuer_email": issuer_email,
                        "number": number, "date": quote_date.strftime("%d/%m/%Y"),
                        "valid_until": valid_until.strftime("%d/%m/%Y"),
                        "client": client, "client_address": client_address,
                        "client_email": client_email, "project": project,
                        "talent": talent["name"], "deliverables": deliverables,
                        "conditions": conditions, "support": prepared["support"],
                        "diffusion": prepared["diffusion"], "territory": prepared["territory"],
                        "duration": prepared["duration"], "exclusivity": prepared["exclusivity"],
                        "pricing": pricing,
                    }
                    quote["html"] = create_quote_html(quote)
                    st.session_state.quotes.append(quote)
                    st.success("Devis généré.")

        for quote in reversed(st.session_state.quotes):
            st.download_button(
                label=f"Télécharger {quote['number']} · {quote['client']} · {euro(quote['pricing']['total_ht'])}",
                data=quote["html"], file_name=f"{quote['number']}.html",
                mime="text/html", key=quote["id"],
            )

with tabs[5]:
    st.subheader("Sauvegarde JSON")
    export_data = {
        "version": 3,
        "exported_at": datetime.now().isoformat(),
        "talents": st.session_state.talents,
        "briefs": st.session_state.briefs,
    }
    st.download_button(
        "Télécharger la sauvegarde",
        json.dumps(export_data, ensure_ascii=False, indent=2),
        "esn_artistique_sauvegarde.json",
        "application/json",
    )

    uploaded = st.file_uploader("Importer une sauvegarde", type=["json"])
    if uploaded:
        try:
            restored = json.loads(uploaded.getvalue().decode("utf-8-sig"))
            for talent in restored.get("talents", []):
                talent["professions"] = as_list(talent.get("professions", talent.get("profession", [])))
                if "day_rate" not in talent:
                    talent["day_rate"] = float(talent.get("rate", 0) or 0)
            for brief in restored.get("briefs", []):
                brief["professions"] = as_list(brief.get("professions", []))

            st.write(
                f"Fichier reconnu : {len(restored.get('talents', []))} talent(s), "
                f"{len(restored.get('briefs', []))} brief(s)."
            )
            if st.button("Restaurer ces données"):
                st.session_state.talents = restored.get("talents", [])
                st.session_state.briefs = restored.get("briefs", [])
                st.session_state.selected_quote = None
                st.session_state.quotes = []
                st.rerun()
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as error:
            st.error(f"Sauvegarde invalide : {error}")
