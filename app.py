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
    "Le client a une enveloppe précise",
    "Le client a une fourchette budgétaire",
    "Le client attend notre estimation",
    "Budget à confirmer",
]
CRITERION_OPTIONS = {
    "Support / usage": [
        "Usage interne", "Site institutionnel", "Réseaux sociaux organiques",
        "Presse éditoriale", "Édition commerciale", "Affichage promotionnel",
        "Campagne publicitaire", "Packaging / merchandising",
    ],
    "Diffusion": [
        "Moins de 1 000 exemplaires / vues", "1 000 à 10 000",
        "10 001 à 100 000", "100 001 à 1 000 000", "Plus de 1 000 000",
    ],
    "Territoire": ["Local / régional", "France", "Europe", "Monde"],
    "Durée": [
        "Opération ponctuelle, 3 mois maximum", "Jusqu'à 1 an",
        "Jusqu'à 3 ans", "Plus de 3 ans",
    ],
    "Exclusivité": [
        "Aucune exclusivité", "Exclusivité limitée à un secteur",
        "Exclusivité territoriale", "Exclusivité totale",
    ],
}
COEFFICIENTS = {
    "Support / usage": [.35, .70, .75, 1, 1.5, 1.75, 3, 2.5],
    "Diffusion": [.5, 1, 2, 4, 8],
    "Territoire": [.7, 1, 1.75, 3],
    "Durée": [.6, 1, 2, 3.5],
    "Exclusivité": [1, 2, 3.5, 6],
}
IMPORTANCE_OPTIONS = {
    "Livrable technique ou accessoire · 20 %": .20,
    "Création standard · 40 %": .40,
    "Création centrale · 60 %": .60,
    "Création à forte valeur commerciale · 80 %": .80,
    "Création signature ou stratégique · 100 %": 1.00,
}
URGENCY_OPTIONS = {
    "Planning normal · 0 %": 0,
    "Délai resserré · 15 %": .15,
    "Urgent · 30 %": .30,
    "Très urgent · 50 %": .50,
    "Priorité absolue · 75 %": .75,
}
MINIMUM_RIGHTS = 100.0

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


def audience_to_diffusion(followers, expected_views):
    audience = max(int(followers or 0), int(expected_views or 0))
    if audience < 1000:
        return CRITERION_OPTIONS["Diffusion"][0]
    if audience <= 10000:
        return CRITERION_OPTIONS["Diffusion"][1]
    if audience <= 100000:
        return CRITERION_OPTIONS["Diffusion"][2]
    if audience <= 1000000:
        return CRITERION_OPTIONS["Diffusion"][3]
    return CRITERION_OPTIONS["Diffusion"][4]


def auto_estimate(brief):
    profiles = max(1, int(brief.get("profile_count", 1) or 1))
    jobs = brief.get("professions", [])
    project_type = (brief.get("project_type") or "").lower()
    deliverables = (brief.get("deliverables") or "").lower()

    prep = float(brief.get("prep_hours_estimate", 0) or 0)
    production = float(brief.get("production_hours_estimate", 0) or 0)
    post = float(brief.get("post_hours_estimate", 0) or 0)
    assumptions = []

    if prep == 0:
        prep = 2 + profiles
        assumptions.append("Préparation estimée par l'abaque interne.")

    if production == 0:
        production = 6 * profiles
        if "vidéo" in project_type or "Vidéaste" in jobs:
            production += 2 * profiles
        if "Graphiste" in jobs or "Illustrateur / Illustratrice" in jobs:
            production += 2 * profiles
        assumptions.append("Production estimée selon les métiers et le nombre de profils.")

    if post == 0:
        post = 2 * profiles
        if "Vidéaste" in jobs:
            post += 4 * profiles
        if "Monteur vidéo" in jobs:
            post += 4 * profiles
        if "Photographe" in jobs:
            post += 2 * profiles
        if "Motion designer" in jobs:
            post += 6 * profiles
        if any(word in deliverables for word in ["plusieurs", "déclinaison", "versions", "série"]):
            post += 3
        assumptions.append("Postproduction estimée selon les métiers et les livrables.")

    if brief.get("multi_role_allowed") == "Oui" and len(jobs) > 1:
        production *= .9
        post *= .9
        assumptions.append("Réduction indicative liée au cumul de métiers.")

    diffusion = brief.get("diffusion_criterion")
    if not diffusion:
        diffusion = audience_to_diffusion(
            brief.get("social_followers"), brief.get("expected_views")
        )
        assumptions.append("Diffusion estimée depuis les abonnés ou les vues attendues.")

    return {
        "preparation_hours": round(prep, 1),
        "production_hours": round(production, 1),
        "postproduction_hours": round(post, 1),
        "preparation_rate": 50.0,
        "production_rate": 75.0,
        "postproduction_rate": 60.0,
        "importance": brief.get("importance_criterion") or "Création centrale · 60 %",
        "urgency": brief.get("urgency_criterion") or "Planning normal · 0 %",
        "selections": {
            "Support / usage": brief.get("support_criterion") or "Réseaux sociaux organiques",
            "Diffusion": diffusion,
            "Territoire": brief.get("territory_criterion") or "France",
            "Durée": brief.get("duration_criterion") or "Jusqu'à 1 an",
            "Exclusivité": brief.get("exclusivity_criterion") or "Aucune exclusivité",
        },
        "expenses": float(brief.get("estimated_expenses", 0) or 0),
        "assumptions": assumptions,
    }


def compute_price(
    prep_hours, production_hours, post_hours,
    prep_rate, production_rate, post_rate,
    importance, urgency, selections,
    expenses, margin_pct, discount_pct,
):
    preparation = prep_hours * prep_rate
    production = production_hours * production_rate
    postproduction = post_hours * post_rate
    creative_cost = preparation + production + postproduction
    base_rights = creative_cost * IMPORTANCE_OPTIONS[importance]
    urgency_amount = creative_cost * URGENCY_OPTIONS[urgency]

    factor = 1.0
    details = []
    for criterion, choice in selections.items():
        index = CRITERION_OPTIONS[criterion].index(choice)
        coefficient = COEFFICIENTS[criterion][index]
        factor *= coefficient
        details.append((criterion, choice, coefficient))

    calculated_rights = base_rights * factor
    rights = max(MINIMUM_RIGHTS, calculated_rights) if base_rights else 0
    subtotal = creative_cost + urgency_amount + rights + expenses
    margin_amount = subtotal * margin_pct / 100
    before_discount = subtotal + margin_amount
    discount_amount = before_discount * discount_pct / 100

    return {
        "preparation": preparation,
        "production": production,
        "postproduction": postproduction,
        "creative_cost": creative_cost,
        "base_rights": base_rights,
        "urgency_amount": urgency_amount,
        "rights_factor": factor,
        "calculated_rights": calculated_rights,
        "rights": rights,
        "minimum_applied": bool(base_rights and calculated_rights < MINIMUM_RIGHTS),
        "expenses": expenses,
        "subtotal_before_margin": subtotal,
        "margin_pct": margin_pct,
        "margin_amount": margin_amount,
        "discount_pct": discount_pct,
        "discount_amount": discount_amount,
        "total": max(0, before_discount - discount_amount),
        "details": details,
    }


def external_ai_prompt(brief):
    jobs = ", ".join(brief.get("professions", [])) or "Non renseignés"
    return f"""Tu agis comme business manager de prestations créatives.

À partir du brief ci-dessous, prépare uniquement les questions encore nécessaires à poser directement au client. Utilise « vous », reste neutre et professionnel, et ne remets pas en cause les choix déjà faits.

RÈGLES
- Maximum 10 questions prioritaires et 6 complémentaires.
- Ne répète pas une information déjà renseignée.
- Il est normal que l'événement précède la date de rendu. Ne présente jamais cet ordre comme une incohérence.
- Ne remets pas en cause le cumul de plusieurs métiers par un même talent.
- Si l'équipe doit être précisée, demande seulement si d'autres profils sont prévus et comment les séquences seront réparties.
- Sépare clairement les questions client des hypothèses internes.

BRIEF
- Client / projet : {brief.get('client')} / {brief.get('title')}
- Date de saisie : {fmt_date(brief.get('brief_date'))}
- Événement : {fmt_date(brief.get('event_date'))}
- Rendu : {fmt_date(brief.get('delivery_date'))}
- Profils / métiers : {brief.get('profile_count')} / {jobs}
- Cumul de métiers : {brief.get('multi_role_allowed')}
- Objectif : {brief.get('business_goal') or 'Non renseigné'}
- Cible : {brief.get('target_audience') or 'Non renseignée'}
- Message : {brief.get('key_message') or 'Non renseigné'}
- Livrables : {brief.get('deliverables') or 'Non renseignés'}
- Budget : {budget_summary(brief)}
- Abonnés : {brief.get('social_followers', 0)}
- Vues attendues : {brief.get('expected_views', 0)}

CRITÈRES DU SIMULATEUR
- Préparation : {brief.get('prep_hours_estimate', 0)} h
- Production : {brief.get('production_hours_estimate', 0)} h
- Postproduction : {brief.get('post_hours_estimate', 0)} h
- Importance : {brief.get('importance_criterion') or 'Non renseignée'}
- Urgence : {brief.get('urgency_criterion') or 'Non renseignée'}
- Support : {brief.get('support_criterion') or 'Non renseigné'}
- Diffusion : {brief.get('diffusion_criterion') or 'À estimer depuis l’audience'}
- Territoire : {brief.get('territory_criterion') or 'Non renseigné'}
- Durée : {brief.get('duration_criterion') or 'Non renseignée'}
- Exclusivité : {brief.get('exclusivity_criterion') or 'Non renseignée'}
- Frais : {euro(brief.get('estimated_expenses'))}

FORMAT
A. 10 questions prioritaires maximum, directement adressées au client.
B. 6 questions complémentaires maximum.
C. Tableau : Critère simulateur | Information connue | Question client à poser.
D. Hypothèses provisoires pour l'estimation, séparées des questions.
E. Informations réellement bloquantes avant devis.
"""


def quote_html(client, project, pricing, notes, validity):
    rows = "".join(
        f"<tr><td>{escape(c)}</td><td>{escape(v)}</td><td>{coef:.2f}</td></tr>"
        for c, v, coef in pricing["details"]
    )
    return f"""<!doctype html><html lang='fr'><head><meta charset='utf-8'>
<style>body{{font-family:Arial;color:#21313D;margin:40px}}table{{border-collapse:collapse;width:100%;margin:16px 0}}th,td{{border:1px solid #CCD6DA;padding:9px}}th{{background:#18354A;color:white}}.total{{font-size:22px;font-weight:bold;color:#0B7E76}}</style></head><body>
<h1>DEVIS INDICATIF</h1><p><b>Client :</b> {escape(client)}<br><b>Projet :</b> {escape(project)}<br><b>Date :</b> {datetime.now().strftime('%d/%m/%Y')}<br><b>Validité :</b> {validity} jours</p>
<table><tr><th>Poste</th><th>Montant HT</th></tr>
<tr><td>Préparation</td><td>{euro(pricing['preparation'])}</td></tr>
<tr><td>Production</td><td>{euro(pricing['production'])}</td></tr>
<tr><td>Postproduction</td><td>{euro(pricing['postproduction'])}</td></tr>
<tr><td>Urgence</td><td>{euro(pricing['urgency_amount'])}</td></tr>
<tr><td>Droits</td><td>{euro(pricing['rights'])}</td></tr>
<tr><td>Frais</td><td>{euro(pricing['expenses'])}</td></tr>
<tr><td>Marge</td><td>{euro(pricing['margin_amount'])}</td></tr>
<tr><td>Remise</td><td>- {euro(pricing['discount_amount'])}</td></tr></table>
<p class='total'>Total HT : {euro(pricing['total'])}</p>
<h2>Droits</h2><table><tr><th>Critère</th><th>Choix</th><th>Coefficient</th></tr>{rows}</table>
<p>{escape(notes).replace(chr(10), '<br>')}</p></body></html>"""


st.markdown("<div class='hero'><h1>🎨 Manager business de créatifs</h1><p>Qualification, estimation, devis et prompt externe.</p></div>", unsafe_allow_html=True)
tabs = st.tabs(["Briefs", "Simulateur", "Devis", "Suivi", "Prompt IA externe", "Sauvegarde"])

with tabs[0]:
    st.header("Brief de mission")
    with st.form("brief_form", clear_on_submit=True):
        st.subheader("1. Repères et dates")
        c1, c2, c3 = st.columns(3)
        brief_date = c1.date_input("Date du jour / date de saisie", value=date.today(), format="DD/MM/YYYY")
        event_date = c2.date_input("Date de l'événement", value=date.today(), format="DD/MM/YYYY")
        delivery_date = c3.date_input("Date de rendu", value=date.today(), format="DD/MM/YYYY")

        c1, c2, c3 = st.columns(3)
        client = c1.text_input("Client *")
        contact = c2.text_input("Contact principal")
        role = c3.text_input("Fonction du contact")
        title = c1.text_input("Projet *")
        project_type = c2.selectbox("Type", ["À préciser", "Photo", "Vidéo", "Graphisme", "Motion design", "Contenu social", "Événement", "Campagne", "Autre"])
        profiles = c3.number_input("Nombre de profils", min_value=1, value=1, step=1)
        jobs = st.multiselect("Métiers nécessaires", PROFESSIONS)
        multi = st.radio("Un profil peut-il cumuler plusieurs métiers ?", ["Oui", "Non", "À confirmer"], horizontal=True)

        st.subheader("2. Besoin")
        c1, c2 = st.columns(2)
        location = c1.text_input("Lieu / zone")
        work_mode = c2.selectbox("Modalité", ["Sur site", "À distance", "Hybride", "À confirmer"])
        goal = c1.text_area("Objectif business / communication")
        target = c2.text_area("Public cible")
        message = c1.text_area("Message / action attendue")
        deliverables = c2.text_area("Livrables")
        skills = c1.text_area("Style, compétences, logiciels")
        references = c2.text_area("Références / contre-exemples")

        st.subheader("3. Critères directs du simulateur")
        c1, c2, c3 = st.columns(3)
        prep_hours = c1.number_input("Heures de préparation estimées", min_value=0.0, step=.5)
        production_hours = c2.number_input("Heures de production estimées", min_value=0.0, step=.5)
        post_hours = c3.number_input("Heures de postproduction estimées", min_value=0.0, step=.5)
        importance = st.selectbox("Importance intrinsèque du rendu", ["À confirmer"] + list(IMPORTANCE_OPTIONS))
        urgency = st.selectbox("Niveau d'urgence", ["À confirmer"] + list(URGENCY_OPTIONS))
        c1, c2 = st.columns(2)
        support = c1.selectbox("Support / usage", ["À confirmer"] + CRITERION_OPTIONS["Support / usage"])
        diffusion = c2.selectbox("Diffusion estimée", ["À estimer depuis l'audience"] + CRITERION_OPTIONS["Diffusion"])
        c1, c2, c3 = st.columns(3)
        followers = c1.number_input("Nombre d'abonnés", min_value=0, step=100)
        views = c2.number_input("Vues / portée attendue", min_value=0, step=1000)
        paid_media = c3.number_input("Achat média HT", min_value=0.0, step=100.0)
        c1, c2, c3 = st.columns(3)
        territory = c1.selectbox("Territoire", ["À confirmer"] + CRITERION_OPTIONS["Territoire"])
        duration = c2.selectbox("Durée d'exploitation", ["À confirmer"] + CRITERION_OPTIONS["Durée"])
        exclusivity = c3.selectbox("Exclusivité", ["À confirmer"] + CRITERION_OPTIONS["Exclusivité"])
        estimated_expenses = st.number_input("Frais déjà estimés HT", min_value=0.0, step=25.0)

        st.subheader("4. Budget et validation")
        budget_mode = st.selectbox("Situation budgétaire", BUDGET_MODES)
        c1, c2 = st.columns(2)
        exact = minimum = maximum = 0.0
        if budget_mode == BUDGET_MODES[0]:
            exact = c1.number_input("Enveloppe précise HT", min_value=0.0, step=100.0)
        elif budget_mode == BUDGET_MODES[1]:
            minimum = c1.number_input("Minimum HT", min_value=0.0, step=100.0)
            maximum = c2.number_input("Maximum HT", min_value=0.0, step=100.0)
        approval = c1.text_area("Décideur final et validation")
        revisions = c2.selectbox("Allers-retours envisagés", ["À confirmer", "1", "2", "3", "Plus de 3"])
        constraints = c1.text_area("Contraintes")
        inputs = c2.text_area("Éléments fournis par le client")
        usage_notes = st.text_area("Précisions sur les droits et utilisations")
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
                    "id": datetime.now().timestamp(), "brief_date": brief_date.isoformat(),
                    "event_date": event_date.isoformat(), "delivery_date": delivery_date.isoformat(),
                    "client": client, "contact_name": contact, "contact_role": role,
                    "title": title, "project_type": project_type, "profile_count": int(profiles),
                    "professions": jobs, "multi_role_allowed": multi, "location": location,
                    "work_mode": work_mode, "business_goal": goal, "target_audience": target,
                    "key_message": message, "deliverables": deliverables, "skills": skills,
                    "references": references, "prep_hours_estimate": prep_hours,
                    "production_hours_estimate": production_hours, "post_hours_estimate": post_hours,
                    "importance_criterion": None if importance == "À confirmer" else importance,
                    "urgency_criterion": None if urgency == "À confirmer" else urgency,
                    "support_criterion": None if support == "À confirmer" else support,
                    "diffusion_criterion": None if diffusion == "À estimer depuis l'audience" else diffusion,
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

    if st.session_state.briefs:
        for index, brief in enumerate(st.session_state.briefs):
            with st.expander(f"{brief['client']} · {brief['title']} · événement {fmt_date(brief.get('event_date'))}"):
                st.write("**Rendu :**", fmt_date(brief.get("delivery_date")))
                st.write("**Audience :**", brief.get("social_followers", 0), "abonnés |", brief.get("expected_views", 0), "vues")
                st.write("**Budget :**", budget_summary(brief))
                if st.button("Supprimer", key=f"delete_{index}"):
                    st.session_state.briefs.pop(index)
                    st.session_state.last_pricing = None
                    st.session_state.last_context = {}
                    st.rerun()

with tabs[1]:
    st.header("Simulateur et estimation automatique")
    brief = None
    estimate = None
    if st.session_state.briefs:
        brief_index = st.selectbox(
            "Brief associé", range(len(st.session_state.briefs)),
            format_func=lambda i: f"{st.session_state.briefs[i]['client']} · {st.session_state.briefs[i]['title']}",
        )
        brief = st.session_state.briefs[brief_index]
        estimate = auto_estimate(brief)
        use_auto = st.checkbox("Utiliser l'estimation automatique comme point de départ", value=True)
        with st.expander("Hypothèses de l'estimation", expanded=True):
            st.write(
                f"Préparation : {estimate['preparation_hours']} h | "
                f"Production : {estimate['production_hours']} h | "
                f"Postproduction : {estimate['postproduction_hours']} h"
            )
            for assumption in estimate["assumptions"]:
                st.write("•", assumption)
    else:
        use_auto = False

    default = estimate if estimate and use_auto else {
        "preparation_hours": 2.0, "production_hours": 8.0, "postproduction_hours": 3.0,
        "preparation_rate": 50.0, "production_rate": 75.0, "postproduction_rate": 60.0,
        "importance": "Création centrale · 60 %", "urgency": "Planning normal · 0 %",
        "selections": {key: values[len(values) // 2] for key, values in CRITERION_OPTIONS.items()},
        "expenses": 0.0,
    }
    widget_key = f"{brief.get('id') if brief else 'manual'}_{use_auto}"
    c1, c2, c3 = st.columns(3)
    prep_h = c1.number_input("Heures préparation", min_value=0.0, value=float(default["preparation_hours"]), step=.5, key="prep_" + widget_key)
    production_h = c2.number_input("Heures production", min_value=0.0, value=float(default["production_hours"]), step=.5, key="production_" + widget_key)
    post_h = c3.number_input("Heures postproduction", min_value=0.0, value=float(default["postproduction_hours"]), step=.5, key="post_" + widget_key)
    c1, c2, c3 = st.columns(3)
    prep_rate = c1.number_input("Tarif préparation / h", min_value=0.0, value=float(default["preparation_rate"]))
    production_rate = c2.number_input("Tarif production / h", min_value=0.0, value=float(default["production_rate"]))
    post_rate = c3.number_input("Tarif postproduction / h", min_value=0.0, value=float(default["postproduction_rate"]))
    importance = st.select_slider("Importance", options=list(IMPORTANCE_OPTIONS), value=default["importance"], key="importance_" + widget_key)
    urgency = st.select_slider("Urgence", options=list(URGENCY_OPTIONS), value=default["urgency"], key="urgency_" + widget_key)
    selections = {}
    for criterion, options in CRITERION_OPTIONS.items():
        selections[criterion] = st.select_slider(
            criterion, options=options, value=default["selections"][criterion],
            key=criterion + "_" + widget_key,
        )
    c1, c2, c3 = st.columns(3)
    expenses = c1.number_input("Frais HT", min_value=0.0, value=float(default["expenses"]))
    margin_pct = c2.number_input("Marge %", min_value=0.0, max_value=100.0, value=10.0)
    discount_pct = c3.number_input("Remise %", min_value=0.0, max_value=100.0, value=0.0)

    pricing = compute_price(
        prep_h, production_h, post_h, prep_rate, production_rate, post_rate,
        importance, urgency, selections, expenses, margin_pct, discount_pct,
    )
    st.session_state.last_pricing = pricing
    st.session_state.last_context = {"brief": brief, "selections": selections}

    metric_columns = st.columns(6)
    metric_values = [
        ("Créatif", pricing["creative_cost"]), ("Base droits", pricing["base_rights"]),
        ("Urgence", pricing["urgency_amount"]), ("Droits", pricing["rights"]),
        ("Marge", pricing["margin_amount"]), ("Total HT", pricing["total"]),
    ]
    for column, (label, value) in zip(metric_columns, metric_values):
        column.metric(label, euro(value))

    st.markdown(
        f"<div class='card'><b>Marge</b><br>Assiette : {euro(pricing['subtotal_before_margin'])}"
        f"<br>Taux : {pricing['margin_pct']:.0f} %<br><b>Montant : {euro(pricing['margin_amount'])}</b></div>",
        unsafe_allow_html=True,
    )

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
            st.session_state.opportunities.append({
                "client": opportunity_client, "project": opportunity_project,
                "status": opportunity_status, "amount": opportunity_amount,
                "next_action": opportunity_next, "notes": opportunity_notes,
            })
    st.dataframe(st.session_state.opportunities, use_container_width=True, hide_index=True)

with tabs[4]:
    st.header("Prompt à utiliser dans une IA externe")
    if not st.session_state.briefs:
        st.info("Crée d'abord un brief.")
    else:
        prompt_index = st.selectbox(
            "Brief à analyser", range(len(st.session_state.briefs)),
            format_func=lambda i: f"{st.session_state.briefs[i]['client']} · {st.session_state.briefs[i]['title']}",
            key="prompt_brief_index",
        )
        prompt = external_ai_prompt(st.session_state.briefs[prompt_index])
        st.text_area("Prompt prêt à copier", value=prompt, height=650)
        st.download_button("Télécharger le prompt", prompt, "prompt_brief_externe.txt", "text/plain")

with tabs[5]:
    st.header("Sauvegarde")
    export = {
        "version": 9, "exported_at": datetime.now().isoformat(),
        "briefs": st.session_state.briefs,
        "opportunities": st.session_state.opportunities,
    }
    st.download_button(
        "Télécharger JSON", json.dumps(export, ensure_ascii=False, indent=2),
        "manager_creatifs.json", "application/json",
    )
    upload = st.file_uploader("Restaurer JSON", type=["json"])
    if upload and st.button("Restaurer"):
        try:
            restored = json.loads(upload.getvalue().decode("utf-8-sig"))
            st.session_state.briefs = restored.get("briefs", [])
            st.session_state.opportunities = restored.get("opportunities", [])
            st.session_state.last_pricing = None
            st.session_state.last_context = {}
            st.rerun()
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as error:
            st.error(f"Fichier invalide : {error}")
