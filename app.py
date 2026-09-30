import json
import re
from datetime import date, datetime
from html import escape

import streamlit as st

st.set_page_config(page_title="Manager de créatifs", page_icon="🎨", layout="wide")
st.markdown(
    """
    <style>
    .block-container{padding-top:1.5rem;padding-bottom:4rem}
    .hero{padding:25px;border-radius:18px;color:white;background:linear-gradient(135deg,#18354D,#25647A);margin-bottom:20px}
    .card{padding:16px;border:1px solid #DDE6EA;border-radius:14px;background:white;margin-bottom:12px}
    .info-card{padding:16px;border-left:5px solid #18A99A;border-radius:10px;background:#EEF9F7;margin:10px 0 18px 0}
    div[data-testid="stMetric"]{border:1px solid #DDE6EA;padding:14px;border-radius:12px;background:white}
    .stButton>button{background:#18A99A;color:white;border:none;font-weight:700}
    </style>
    """,
    unsafe_allow_html=True,
)

PROFESSIONS = [
    "Photographe", "Vidéaste", "Monteur vidéo", "Pilote de drone", "Graphiste",
    "Motion designer", "Directeur artistique", "Community manager",
    "Maquilleur / Maquilleuse", "Styliste", "Illustrateur / Illustratrice",
    "Retoucheur / Retoucheuse", "Sound designer", "Ingénieur du son",
    "Rédacteur / Rédactrice",
]
BUDGET_MODES = [
    "Le client a une enveloppe précise", "Le client a une fourchette budgétaire",
    "Le client attend notre estimation", "Budget à confirmer",
]
PROJECT_MODES = ["Petit projet", "Projet standard"]

MODE_EXPLANATIONS = {
    "Petit projet": (
        "Mission légère et ciblée : contenu organique, shooting court, petite captation, "
        "Reel simple, montage léger, diffusion limitée et peu d'enjeux publicitaires. "
        "Le prix repose surtout sur le temps de travail, avec des droits modérés."
    ),
    "Projet standard": (
        "Mission avec plusieurs livrables ou une exploitation plus structurée : contenu principal, "
        "communication de marque, plusieurs formats, audience plus large, campagne payante, "
        "vente de produits ou droits plus étendus."
    ),
}

SUPPORT_OPTIONS = [
    "Usage interne", "Site institutionnel", "Réseaux sociaux organiques",
    "Presse éditoriale", "Édition commerciale", "Affichage promotionnel",
    "Campagne publicitaire", "Packaging / merchandising",
]
TERRITORY_OPTIONS = ["Local / régional", "France", "Europe", "Monde"]
DURATION_OPTIONS = [
    "Opération ponctuelle, 3 mois maximum", "Jusqu'à 1 an",
    "Jusqu'à 3 ans", "Plus de 3 ans",
]
EXCLUSIVITY_OPTIONS = [
    "Aucune exclusivité", "Exclusivité limitée à un secteur",
    "Exclusivité territoriale", "Exclusivité totale",
]
USAGE_TYPES = [
    "Audience / vues numériques",
    "Tirage / exemplaires imprimés",
    "Ventes de produits / unités vendues",
    "Usage interne / nombre de personnes",
]

USAGE_BANDS = {
    "Audience / vues numériques": [
        "Moins de 1 000 vues", "1 000 à 10 000 vues", "10 001 à 100 000 vues",
        "100 001 à 1 000 000 vues", "Plus de 1 000 000 vues",
    ],
    "Tirage / exemplaires imprimés": [
        "Moins de 100 exemplaires", "100 à 500 exemplaires", "501 à 2 000 exemplaires",
        "2 001 à 10 000 exemplaires", "Plus de 10 000 exemplaires",
    ],
    "Ventes de produits / unités vendues": [
        "Moins de 100 ventes", "100 à 500 ventes", "501 à 2 000 ventes",
        "2 001 à 10 000 ventes", "Plus de 10 000 ventes",
    ],
    "Usage interne / nombre de personnes": [
        "Moins de 50 personnes", "50 à 250 personnes", "251 à 1 000 personnes",
        "1 001 à 5 000 personnes", "Plus de 5 000 personnes",
    ],
}

MODE_CONFIG = {
    "Petit projet": {
        "importance": {
            "Livrable technique ou accessoire · 5 %": .05,
            "Création standard · 10 %": .10,
            "Création centrale · 15 %": .15,
            "Création à valeur commerciale · 20 %": .20,
            "Création signature ou stratégique · 30 %": .30,
        },
        "urgency": {
            "Planning normal · 0 %": 0,
            "Délai resserré · 5 %": .05,
            "Urgent · 10 %": .10,
            "Très urgent · 20 %": .20,
            "Priorité absolue · 30 %": .30,
        },
        "support": [.50, .70, .75, .80, .90, 1.00, 1.30, 1.20],
        "usage": [.60, .75, 1.00, 1.30, 1.80],
        "territory": [.70, 1.00, 1.20, 1.50],
        "duration": [.70, 1.00, 1.25, 1.60],
        "exclusivity": [1.00, 1.20, 1.40, 1.80],
        "minimum_rights": 40.0,
        "default_importance": "Création standard · 10 %",
    },
    "Projet standard": {
        "importance": {
            "Livrable technique ou accessoire · 15 %": .15,
            "Création standard · 30 %": .30,
            "Création centrale · 45 %": .45,
            "Création à forte valeur commerciale · 60 %": .60,
            "Création signature ou stratégique · 80 %": .80,
        },
        "urgency": {
            "Planning normal · 0 %": 0,
            "Délai resserré · 10 %": .10,
            "Urgent · 20 %": .20,
            "Très urgent · 35 %": .35,
            "Priorité absolue · 50 %": .50,
        },
        "support": [.25, .50, .60, .80, 1.10, 1.25, 1.80, 1.50],
        "usage": [.35, .70, 1.20, 2.20, 4.00],
        "territory": [.50, .85, 1.25, 2.00],
        "duration": [.45, .80, 1.30, 2.10],
        "exclusivity": [1.00, 1.40, 2.00, 3.00],
        "minimum_rights": 75.0,
        "default_importance": "Création centrale · 45 %",
    },
}

for key, default in {
    "briefs": [], "opportunities": [], "last_pricing": None, "last_context": {}
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


def euro(value):
    return f"{float(value or 0):,.2f} €".replace(",", " ").replace(".", ",")


def fmt_date(value):
    if not value:
        return "Non renseignée"
    try:
        return datetime.fromisoformat(value).strftime("%d/%m/%Y")
    except (TypeError, ValueError):
        return str(value)


def budget_summary(brief):
    mode = brief.get("budget_mode", "Budget à confirmer")
    if mode == BUDGET_MODES[0]:
        return f"{mode} : {euro(brief.get('budget_exact'))}"
    if mode == BUDGET_MODES[1]:
        return f"{mode} : {euro(brief.get('budget_min'))} à {euro(brief.get('budget_max'))}"
    return mode


def quantity_to_band(usage_type, quantity):
    quantity = int(quantity or 0)
    if usage_type == "Audience / vues numériques":
        limits = [1000, 10000, 100000, 1000000]
    elif usage_type == "Tirage / exemplaires imprimés":
        limits = [100, 500, 2000, 10000]
    elif usage_type == "Ventes de produits / unités vendues":
        limits = [100, 500, 2000, 10000]
    else:
        limits = [50, 250, 1000, 5000]
    for index, limit in enumerate(limits):
        if quantity < limit if index == 0 else quantity <= limit:
            return USAGE_BANDS[usage_type][index]
    return USAGE_BANDS[usage_type][4]


def auto_estimate(brief, pricing_mode):
    profiles = max(1, int(brief.get("profile_count", 1) or 1))
    jobs = brief.get("professions", [])
    project_type = (brief.get("project_type") or "").lower()
    deliverables = (brief.get("deliverables") or "").lower()
    assumptions = []

    preparation = float(brief.get("prep_hours_estimate", 0) or 0)
    production = float(brief.get("production_hours_estimate", 0) or 0)
    postproduction = float(brief.get("post_hours_estimate", 0) or 0)

    if preparation == 0:
        preparation = 2 + profiles
        assumptions.append("Préparation estimée par l'abaque interne.")
    if production == 0:
        production = 6 * profiles
        if "vidéo" in project_type or "Vidéaste" in jobs:
            production += 2 * profiles
        if "Graphiste" in jobs or "Illustrateur / Illustratrice" in jobs:
            production += 2 * profiles
        assumptions.append("Production estimée selon les métiers et le nombre de profils.")
    if postproduction == 0:
        postproduction = 2 * profiles
        if "Vidéaste" in jobs:
            postproduction += 4 * profiles
        if "Monteur vidéo" in jobs:
            postproduction += 4 * profiles
        if "Photographe" in jobs:
            postproduction += 2 * profiles
        if "Motion designer" in jobs:
            postproduction += 6 * profiles
        if any(word in deliverables for word in ["plusieurs", "déclinaison", "versions", "série"]):
            postproduction += 3
        assumptions.append("Postproduction estimée selon les métiers et les livrables.")
    if brief.get("multi_role_allowed") == "Oui" and len(jobs) > 1:
        production *= .9
        postproduction *= .9
        assumptions.append("Réduction indicative liée au cumul de métiers.")

    usage_type = brief.get("usage_type") or "Audience / vues numériques"
    usage_quantity = int(brief.get("usage_quantity", 0) or 0)
    usage_band = quantity_to_band(usage_type, usage_quantity)
    assumptions.append(f"Niveau d'utilisation calculé selon : {usage_type.lower()}.")

    config = MODE_CONFIG[pricing_mode]
    return {
        "preparation_hours": round(preparation, 1),
        "production_hours": round(production, 1),
        "postproduction_hours": round(postproduction, 1),
        "preparation_rate": 50.0,
        "production_rate": 75.0,
        "postproduction_rate": 60.0,
        "importance": brief.get("importance_criterion") if brief.get("pricing_mode") == pricing_mode else None,
        "urgency": brief.get("urgency_criterion") if brief.get("pricing_mode") == pricing_mode else None,
        "support": brief.get("support_criterion") or "Réseaux sociaux organiques",
        "usage_type": usage_type,
        "usage_band": usage_band,
        "territory": brief.get("territory_criterion") or "France",
        "duration": brief.get("duration_criterion") or "Jusqu'à 1 an",
        "exclusivity": brief.get("exclusivity_criterion") or "Aucune exclusivité",
        "expenses": float(brief.get("estimated_expenses", 0) or 0),
        "assumptions": assumptions,
        "default_importance": config["default_importance"],
    }


def compute_price(
    pricing_mode, prep_hours, production_hours, post_hours,
    prep_rate, production_rate, post_rate, importance, urgency,
    support, usage_type, usage_band, territory, duration, exclusivity,
    expenses, margin_pct, discount_pct,
):
    config = MODE_CONFIG[pricing_mode]
    preparation = prep_hours * prep_rate
    production = production_hours * production_rate
    postproduction = post_hours * post_rate
    creative_cost = preparation + production + postproduction
    base_rights = creative_cost * config["importance"][importance]
    urgency_amount = creative_cost * config["urgency"][urgency]

    details = []
    factors = [
        ("Support / usage", support, config["support"][SUPPORT_OPTIONS.index(support)]),
        (usage_type, usage_band, config["usage"][USAGE_BANDS[usage_type].index(usage_band)]),
        ("Territoire", territory, config["territory"][TERRITORY_OPTIONS.index(territory)]),
        ("Durée", duration, config["duration"][DURATION_OPTIONS.index(duration)]),
        ("Exclusivité", exclusivity, config["exclusivity"][EXCLUSIVITY_OPTIONS.index(exclusivity)]),
    ]
    factor = 1.0
    for criterion, choice, coefficient in factors:
        factor *= coefficient
        details.append((criterion, choice, coefficient))

    calculated_rights = base_rights * factor
    rights = max(config["minimum_rights"], calculated_rights) if base_rights else 0
    subtotal = creative_cost + urgency_amount + rights + expenses
    margin_amount = subtotal * margin_pct / 100
    before_discount = subtotal + margin_amount
    discount_amount = before_discount * discount_pct / 100

    return {
        "pricing_mode": pricing_mode,
        "preparation": preparation, "production": production,
        "postproduction": postproduction, "creative_cost": creative_cost,
        "base_rights": base_rights, "urgency_amount": urgency_amount,
        "rights_factor": factor, "calculated_rights": calculated_rights,
        "rights": rights, "minimum_rights": config["minimum_rights"],
        "minimum_applied": bool(base_rights and calculated_rights < config["minimum_rights"]),
        "expenses": expenses, "subtotal_before_margin": subtotal,
        "margin_pct": margin_pct, "margin_amount": margin_amount,
        "discount_pct": discount_pct, "discount_amount": discount_amount,
        "total": max(0, before_discount - discount_amount), "details": details,
    }


def external_prompt(brief):
    jobs = ", ".join(brief.get("professions", [])) or "Non renseignés"
    return f"""Tu agis comme business manager de prestations créatives. À partir du brief ci-dessous, prépare uniquement les questions encore nécessaires à poser directement au client. Utilise « vous », reste neutre et professionnel.

RÈGLES
- Maximum 10 questions prioritaires et 6 complémentaires.
- Ne répète pas une information déjà renseignée.
- Il est normal que l'événement précède la date de rendu.
- Ne remets pas en cause le cumul de plusieurs métiers par un même talent.
- Pour l'utilisation, distingue impérativement audience numérique, tirage imprimé, unités vendues et usage interne.

BRIEF
- Client / projet : {brief.get('client')} / {brief.get('title')}
- Mode tarifaire : {brief.get('pricing_mode') or 'Non renseigné'}
- Événement : {fmt_date(brief.get('event_date'))}
- Rendu : {fmt_date(brief.get('delivery_date'))}
- Profils / métiers : {brief.get('profile_count')} / {jobs}
- Objectif : {brief.get('business_goal') or 'Non renseigné'}
- Livrables : {brief.get('deliverables') or 'Non renseignés'}
- Budget : {budget_summary(brief)}
- Type d'utilisation : {brief.get('usage_type') or 'Non renseigné'}
- Quantité d'utilisation : {brief.get('usage_quantity', 0)}
- Abonnés : {brief.get('social_followers', 0)}
- Vues attendues : {brief.get('expected_views', 0)}

SIMULATEUR
- Préparation : {brief.get('prep_hours_estimate', 0)} h
- Production : {brief.get('production_hours_estimate', 0)} h
- Postproduction : {brief.get('post_hours_estimate', 0)} h
- Support : {brief.get('support_criterion') or 'Non renseigné'}
- Territoire : {brief.get('territory_criterion') or 'Non renseigné'}
- Durée : {brief.get('duration_criterion') or 'Non renseignée'}
- Exclusivité : {brief.get('exclusivity_criterion') or 'Non renseignée'}

FORMAT
A. Questions prioritaires.
B. Questions complémentaires.
C. Tableau : Critère simulateur | Information connue | Question client.
D. Hypothèses provisoires séparées des questions.
E. Informations réellement bloquantes avant devis.
"""


def quote_html(client, project, pricing, notes, validity):
    rows = "".join(
        f"<tr><td>{escape(c)}</td><td>{escape(v)}</td><td>{coef:.2f}</td></tr>"
        for c, v, coef in pricing["details"]
    )
    return f"""<!doctype html><html lang='fr'><head><meta charset='utf-8'><style>
body{{font-family:Arial;color:#21313D;margin:40px}}table{{border-collapse:collapse;width:100%;margin:16px 0}}th,td{{border:1px solid #CCD6DA;padding:9px}}th{{background:#18354A;color:white}}.total{{font-size:22px;font-weight:bold;color:#0B7E76}}</style></head><body>
<h1>DEVIS INDICATIF</h1><p><b>Client :</b> {escape(client)}<br><b>Projet :</b> {escape(project)}<br><b>Mode :</b> {escape(pricing['pricing_mode'])}<br><b>Date :</b> {datetime.now().strftime('%d/%m/%Y')}<br><b>Validité :</b> {validity} jours</p>
<table><tr><th>Poste</th><th>Montant HT</th></tr><tr><td>Préparation</td><td>{euro(pricing['preparation'])}</td></tr><tr><td>Production</td><td>{euro(pricing['production'])}</td></tr><tr><td>Postproduction</td><td>{euro(pricing['postproduction'])}</td></tr><tr><td>Urgence</td><td>{euro(pricing['urgency_amount'])}</td></tr><tr><td>Droits</td><td>{euro(pricing['rights'])}</td></tr><tr><td>Frais</td><td>{euro(pricing['expenses'])}</td></tr><tr><td>Marge</td><td>{euro(pricing['margin_amount'])}</td></tr><tr><td>Remise</td><td>- {euro(pricing['discount_amount'])}</td></tr></table>
<p class='total'>Total HT : {euro(pricing['total'])}</p><h2>Droits</h2><table><tr><th>Critère</th><th>Choix</th><th>Coefficient</th></tr>{rows}</table><p>{escape(notes).replace(chr(10), '<br>')}</p></body></html>"""


st.markdown("<div class='hero'><h1>🎨 Manager business de créatifs</h1><p>Qualification, estimation, devis et prompt externe.</p></div>", unsafe_allow_html=True)
tabs = st.tabs(["Briefs", "Simulateur", "Devis", "Suivi", "Prompt IA externe", "Sauvegarde"])

with tabs[0]:
    st.header("Brief de mission")
    st.markdown(
        "<div class='info-card'><b>Petit projet</b> : contenu simple, organique, diffusion limitée, peu de livrables et droits modérés.<br>"
        "<b>Projet standard</b> : plusieurs livrables, exploitation commerciale, campagne payante, vente de produits ou diffusion plus large.</div>",
        unsafe_allow_html=True,
    )
    with st.form("brief_form", clear_on_submit=True):
        pricing_mode = st.selectbox("Catégorie tarifaire du projet", PROJECT_MODES)
        c1, c2, c3 = st.columns(3)
        brief_date = c1.date_input("Date de saisie", date.today(), format="DD/MM/YYYY")
        event_date = c2.date_input("Date de l'événement", date.today(), format="DD/MM/YYYY")
        delivery_date = c3.date_input("Date de rendu", date.today(), format="DD/MM/YYYY")
        c1, c2, c3 = st.columns(3)
        client = c1.text_input("Client *")
        contact = c2.text_input("Contact principal")
        role = c3.text_input("Fonction")
        title = c1.text_input("Projet *")
        project_type = c2.selectbox("Type", ["À préciser", "Photo", "Vidéo", "Graphisme", "Motion design", "Contenu social", "Événement", "Campagne", "Autre"])
        profiles = c3.number_input("Nombre de profils", min_value=1, value=1)
        jobs = st.multiselect("Métiers nécessaires", PROFESSIONS)
        multi = st.radio("Un profil peut-il cumuler plusieurs métiers ?", ["Oui", "Non", "À confirmer"], horizontal=True)

        c1, c2 = st.columns(2)
        location = c1.text_input("Lieu / zone")
        work_mode = c2.selectbox("Modalité", ["Sur site", "À distance", "Hybride", "À confirmer"])
        goal = c1.text_area("Objectif")
        target = c2.text_area("Public cible")
        message = c1.text_area("Message")
        deliverables = c2.text_area("Livrables")
        skills = c1.text_area("Style / compétences")
        references = c2.text_area("Références")

        st.subheader("Critères directs du simulateur")
        c1, c2, c3 = st.columns(3)
        prep_hours = c1.number_input("Heures préparation", min_value=0.0, step=.5)
        production_hours = c2.number_input("Heures production", min_value=0.0, step=.5)
        post_hours = c3.number_input("Heures postproduction", min_value=0.0, step=.5)
        support = st.selectbox("Support", ["À confirmer"] + SUPPORT_OPTIONS)
        c1, c2 = st.columns(2)
        usage_type = c1.selectbox("Nature de l'utilisation", USAGE_TYPES)
        usage_quantity = c2.number_input("Nombre de vues, exemplaires, ventes ou personnes", min_value=0, step=100)
        c1, c2, c3 = st.columns(3)
        followers = c1.number_input("Abonnés", min_value=0, step=100)
        views = c2.number_input("Vues attendues", min_value=0, step=1000)
        paid_media = c3.number_input("Achat média HT", min_value=0.0, step=100.0)
        territory = c1.selectbox("Territoire", ["À confirmer"] + TERRITORY_OPTIONS)
        duration = c2.selectbox("Durée", ["À confirmer"] + DURATION_OPTIONS)
        exclusivity = c3.selectbox("Exclusivité", ["À confirmer"] + EXCLUSIVITY_OPTIONS)
        estimated_expenses = st.number_input("Frais estimés HT", min_value=0.0, step=25.0)

        budget_mode = st.selectbox("Situation budgétaire", BUDGET_MODES)
        c1, c2 = st.columns(2)
        exact = minimum = maximum = 0.0
        if budget_mode == BUDGET_MODES[0]:
            exact = c1.number_input("Enveloppe HT", min_value=0.0, step=100.0)
        elif budget_mode == BUDGET_MODES[1]:
            minimum = c1.number_input("Minimum HT", min_value=0.0, step=100.0)
            maximum = c2.number_input("Maximum HT", min_value=0.0, step=100.0)
        approval = c1.text_area("Décideur et validation")
        revisions = c2.selectbox("Allers-retours", ["À confirmer", "1", "2", "3", "Plus de 3"])
        constraints = c1.text_area("Contraintes")
        inputs = c2.text_area("Éléments fournis")
        usage_notes = st.text_area("Droits et utilisations")
        description = st.text_area("Informations complémentaires")

        if st.form_submit_button("Créer le brief"):
            if not client or not title:
                st.error("Client et projet obligatoires.")
            elif delivery_date < event_date:
                st.error("La date de rendu ne peut pas précéder l'événement.")
            elif budget_mode == BUDGET_MODES[1] and maximum and minimum > maximum:
                st.error("Le minimum dépasse le maximum.")
            else:
                st.session_state.briefs.append({
                    "id": datetime.now().timestamp(), "pricing_mode": pricing_mode,
                    "brief_date": brief_date.isoformat(), "event_date": event_date.isoformat(),
                    "delivery_date": delivery_date.isoformat(), "client": client,
                    "contact_name": contact, "contact_role": role, "title": title,
                    "project_type": project_type, "profile_count": int(profiles),
                    "professions": jobs, "multi_role_allowed": multi, "location": location,
                    "work_mode": work_mode, "business_goal": goal, "target_audience": target,
                    "key_message": message, "deliverables": deliverables, "skills": skills,
                    "references": references, "prep_hours_estimate": prep_hours,
                    "production_hours_estimate": production_hours, "post_hours_estimate": post_hours,
                    "support_criterion": None if support == "À confirmer" else support,
                    "usage_type": usage_type, "usage_quantity": int(usage_quantity),
                    "social_followers": int(followers), "expected_views": int(views),
                    "paid_media_budget": paid_media,
                    "territory_criterion": None if territory == "À confirmer" else territory,
                    "duration_criterion": None if duration == "À confirmer" else duration,
                    "exclusivity_criterion": None if exclusivity == "À confirmer" else exclusivity,
                    "estimated_expenses": estimated_expenses, "budget_mode": budget_mode,
                    "budget_exact": exact, "budget_min": minimum, "budget_max": maximum,
                    "approval_process": approval, "revision_rounds": revisions,
                    "constraints": constraints, "client_inputs": inputs,
                    "usage_notes": usage_notes, "description": description,
                })
                st.success("Brief créé.")

    for index, brief in enumerate(st.session_state.briefs):
        with st.expander(f"{brief['client']} · {brief['title']} · {brief.get('pricing_mode', 'Projet standard')}"):
            st.write("**Événement :**", fmt_date(brief.get("event_date")), "| **Rendu :**", fmt_date(brief.get("delivery_date")))
            st.write("**Utilisation :**", brief.get("usage_type", "Non renseignée"), "|", brief.get("usage_quantity", 0))
            st.write("**Budget :**", budget_summary(brief))
            if st.button("Supprimer", key=f"delete_{index}"):
                st.session_state.briefs.pop(index)
                st.session_state.last_pricing = None
                st.session_state.last_context = {}
                st.rerun()

with tabs[1]:
    st.header("Simulateur")
    st.markdown(
        "<div class='info-card'><b>Choisis Petit projet</b> pour un contenu simple et une exploitation limitée. "
        "<b>Choisis Projet standard</b> lorsqu'il y a plusieurs livrables, de la publicité, de la vente de produits ou des droits étendus.</div>",
        unsafe_allow_html=True,
    )
    brief = None
    estimate = None
    if st.session_state.briefs:
        brief_index = st.selectbox("Brief associé", range(len(st.session_state.briefs)), format_func=lambda i: f"{st.session_state.briefs[i]['client']} · {st.session_state.briefs[i]['title']}")
        brief = st.session_state.briefs[brief_index]
        default_mode = brief.get("pricing_mode", "Projet standard")
    else:
        default_mode = "Petit projet"

    pricing_mode = st.radio("Mode tarifaire", PROJECT_MODES, index=PROJECT_MODES.index(default_mode), horizontal=True)
    if brief:
        estimate = auto_estimate(brief, pricing_mode)
        use_auto = st.checkbox("Utiliser l'estimation automatique comme point de départ", value=True)
        with st.expander("Hypothèses", expanded=True):
            st.write(f"Préparation : {estimate['preparation_hours']} h | Production : {estimate['production_hours']} h | Postproduction : {estimate['postproduction_hours']} h")
            for assumption in estimate["assumptions"]:
                st.write("•", assumption)
    else:
        use_auto = False

    config = MODE_CONFIG[pricing_mode]
    default = estimate if estimate and use_auto else {
        "preparation_hours": 2.0, "production_hours": 8.0, "postproduction_hours": 3.0,
        "preparation_rate": 50.0, "production_rate": 75.0, "postproduction_rate": 60.0,
        "importance": None, "urgency": None, "support": "Réseaux sociaux organiques",
        "usage_type": "Audience / vues numériques", "usage_band": USAGE_BANDS["Audience / vues numériques"][1],
        "territory": "France", "duration": "Jusqu'à 1 an",
        "exclusivity": "Aucune exclusivité", "expenses": 0.0,
        "default_importance": config["default_importance"],
    }
    widget_key = f"{brief.get('id') if brief else 'manual'}_{pricing_mode}_{use_auto}"
    c1, c2, c3 = st.columns(3)
    prep_h = c1.number_input("Heures préparation", min_value=0.0, value=float(default["preparation_hours"]), step=.5, key="prep_" + widget_key)
    production_h = c2.number_input("Heures production", min_value=0.0, value=float(default["production_hours"]), step=.5, key="production_" + widget_key)
    post_h = c3.number_input("Heures postproduction", min_value=0.0, value=float(default["postproduction_hours"]), step=.5, key="post_" + widget_key)
    c1, c2, c3 = st.columns(3)
    prep_rate = c1.number_input("Tarif préparation / h", min_value=0.0, value=float(default["preparation_rate"]))
    production_rate = c2.number_input("Tarif production / h", min_value=0.0, value=float(default["production_rate"]))
    post_rate = c3.number_input("Tarif postproduction / h", min_value=0.0, value=float(default["postproduction_rate"]))

    importance_default = default.get("importance") if default.get("importance") in config["importance"] else config["default_importance"]
    urgency_default = default.get("urgency") if default.get("urgency") in config["urgency"] else list(config["urgency"])[0]
    importance = st.select_slider("Importance", options=list(config["importance"]), value=importance_default, key="importance_" + widget_key)
    urgency = st.select_slider("Urgence", options=list(config["urgency"]), value=urgency_default, key="urgency_" + widget_key)
    support = st.select_slider("Support / usage", options=SUPPORT_OPTIONS, value=default["support"], key="support_" + widget_key)
    usage_type = st.selectbox("Nature de l'utilisation", USAGE_TYPES, index=USAGE_TYPES.index(default["usage_type"]), key="usage_type_" + widget_key)
    usage_default = default["usage_band"] if default["usage_type"] == usage_type and default["usage_band"] in USAGE_BANDS[usage_type] else USAGE_BANDS[usage_type][1]
    usage_band = st.select_slider("Niveau d'utilisation", options=USAGE_BANDS[usage_type], value=usage_default, key="usage_band_" + widget_key)
    territory = st.select_slider("Territoire", options=TERRITORY_OPTIONS, value=default["territory"], key="territory_" + widget_key)
    duration = st.select_slider("Durée", options=DURATION_OPTIONS, value=default["duration"], key="duration_" + widget_key)
    exclusivity = st.select_slider("Exclusivité", options=EXCLUSIVITY_OPTIONS, value=default["exclusivity"], key="exclusivity_" + widget_key)

    c1, c2, c3 = st.columns(3)
    expenses = c1.number_input("Frais HT", min_value=0.0, value=float(default["expenses"]))
    margin_pct = c2.number_input("Marge %", min_value=0.0, max_value=100.0, value=10.0)
    discount_pct = c3.number_input("Remise %", min_value=0.0, max_value=100.0, value=0.0)

    pricing = compute_price(
        pricing_mode, prep_h, production_h, post_h, prep_rate, production_rate,
        post_rate, importance, urgency, support, usage_type, usage_band,
        territory, duration, exclusivity, expenses, margin_pct, discount_pct,
    )
    st.session_state.last_pricing = pricing
    st.session_state.last_context = {"brief": brief}

    metric_columns = st.columns(6)
    values = [
        ("Créatif", pricing["creative_cost"]), ("Base droits", pricing["base_rights"]),
        ("Urgence", pricing["urgency_amount"]), ("Droits", pricing["rights"]),
        ("Marge", pricing["margin_amount"]), ("Total HT", pricing["total"]),
    ]
    for column, (label, value) in zip(metric_columns, values):
        column.metric(label, euro(value))
    if pricing["minimum_applied"]:
        st.info(f"Minimum de droits appliqué pour le mode {pricing_mode} : {euro(pricing['minimum_rights'])}")

with tabs[2]:
    st.header("Devis")
    pricing = st.session_state.last_pricing
    context = st.session_state.last_context or {}
    if not pricing:
        st.info("Calcule d'abord une estimation.")
    else:
        brief = context.get("brief") or {}
        client = st.text_input("Client", value=brief.get("client", ""), key="quote_client")
        project = st.text_input("Projet", value=brief.get("title", ""), key="quote_project")
        validity = st.number_input("Validité jours", min_value=1, max_value=365, value=30)
        notes = st.text_area("Notes", value="Acompte, dates, livrables, retours et droits à confirmer.")
        html = quote_html(client, project, pricing, notes, validity)
        filename = re.sub(r"[^a-zA-Z0-9]+", "_", project or "projet")
        st.download_button("Télécharger devis HTML", html.encode("utf-8"), f"devis_{filename}.html", "text/html")

with tabs[3]:
    st.header("Suivi")
    with st.form("opportunity_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        opportunity_client = c1.text_input("Client")
        opportunity_project = c2.text_input("Projet")
        opportunity_status = c3.selectbox("Statut", ["À qualifier", "Estimation", "Devis envoyé", "Relance", "Gagné", "Perdu"])
        opportunity_amount = c1.number_input("Montant HT", min_value=0.0)
        opportunity_next = c2.text_input("Prochaine action")
        opportunity_notes = c3.text_input("Notes")
        if st.form_submit_button("Ajouter"):
            st.session_state.opportunities.append({"client": opportunity_client, "project": opportunity_project, "status": opportunity_status, "amount": opportunity_amount, "next_action": opportunity_next, "notes": opportunity_notes})
    st.dataframe(st.session_state.opportunities, use_container_width=True, hide_index=True)

with tabs[4]:
    st.header("Prompt pour IA externe")
    if not st.session_state.briefs:
        st.info("Crée d'abord un brief.")
    else:
        prompt_index = st.selectbox("Brief", range(len(st.session_state.briefs)), format_func=lambda i: f"{st.session_state.briefs[i]['client']} · {st.session_state.briefs[i]['title']}", key="prompt_index")
        prompt = external_prompt(st.session_state.briefs[prompt_index])
        st.text_area("Prompt prêt à copier", value=prompt, height=650)
        st.download_button("Télécharger le prompt", prompt, "prompt_externe.txt", "text/plain")

with tabs[5]:
    st.header("Sauvegarde")
    export = {"version": 11, "exported_at": datetime.now().isoformat(), "briefs": st.session_state.briefs, "opportunities": st.session_state.opportunities}
    st.download_button("Télécharger JSON", json.dumps(export, ensure_ascii=False, indent=2), "manager_creatifs.json", "application/json")
    upload = st.file_uploader("Restaurer JSON", type=["json"])
    if upload and st.button("Restaurer"):
        try:
            data = json.loads(upload.getvalue().decode("utf-8-sig"))
            st.session_state.briefs = data.get("briefs", [])
            st.session_state.opportunities = data.get("opportunities", [])
            st.session_state.last_pricing = None
            st.session_state.last_context = {}
            st.rerun()
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as error:
            st.error(f"Fichier invalide : {error}")
