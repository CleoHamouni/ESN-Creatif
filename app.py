import json
import re
from datetime import datetime
from html import escape

import streamlit as st

st.set_page_config(page_title="Manager de créatifs", page_icon="🎨", layout="wide")

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.8rem; padding-bottom: 4rem;}
    .main-title {padding: 24px; border-radius: 18px; color: white;
        background: linear-gradient(135deg,#18354D,#25647A); margin-bottom: 18px;}
    .card {padding: 16px; border: 1px solid #DDE6EA; border-radius: 14px;
        background: white; margin-bottom: 12px;}
    .small {color:#65727A; font-size:14px;}
    div[data-testid="stMetric"] {border:1px solid #DDE6EA; padding:14px;
        border-radius:12px; background:white;}
    .stButton > button {background:#18A99A; color:white; border:none; font-weight:700;}
    </style>
    """,
    unsafe_allow_html=True,
)

PROFESSIONS = [
    "Photographe", "Vidéaste", "Monteur vidéo", "Pilote de drone",
    "Graphiste", "Motion designer", "Directeur artistique",
    "Community manager", "Maquilleur / Maquilleuse", "Styliste",
    "Illustrateur / Illustratrice", "Retoucheur / Retoucheuse",
    "Sound designer", "Ingénieur du son", "Rédacteur / Rédactrice",
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
    "Support / usage": [0.35, 0.70, 0.75, 1.00, 1.50, 1.75, 3.00, 2.50],
    "Diffusion": [0.50, 1.00, 2.00, 4.00, 8.00],
    "Territoire": [0.70, 1.00, 1.75, 3.00],
    "Durée": [0.60, 1.00, 2.00, 3.50],
    "Exclusivité": [1.00, 2.00, 3.50, 6.00],
}

IMPORTANCE_OPTIONS = {
    "Livrable technique ou accessoire · 20 %": 0.20,
    "Création standard · 40 %": 0.40,
    "Création centrale · 60 %": 0.60,
    "Création à forte valeur commerciale · 80 %": 0.80,
    "Création signature ou stratégique · 100 %": 1.00,
}

URGENCY_OPTIONS = {
    "Planning normal · 0 %": 0.00,
    "Délai resserré · 15 %": 0.15,
    "Urgent · 30 %": 0.30,
    "Très urgent · 50 %": 0.50,
    "Priorité absolue · 75 %": 0.75,
}

MINIMUM_RIGHTS = 100.0


def init_state():
    defaults = {
        "briefs": [],
        "opportunities": [],
        "last_pricing": None,
        "last_context": {},
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_state()


def euro(value):
    return f"{float(value or 0):,.2f} €".replace(",", " ").replace(".", ",")


def compute_price(
    preparation_hours,
    production_hours,
    postproduction_hours,
    preparation_rate,
    production_rate,
    postproduction_rate,
    importance_label,
    urgency_label,
    selections,
    expenses,
    margin_pct,
    discount_pct,
):
    preparation = preparation_hours * preparation_rate
    production = production_hours * production_rate
    postproduction = postproduction_hours * postproduction_rate
    creative_cost = preparation + production + postproduction

    importance_rate = IMPORTANCE_OPTIONS[importance_label]
    urgency_rate = URGENCY_OPTIONS[urgency_label]
    base_rights = creative_cost * importance_rate
    urgency_amount = creative_cost * urgency_rate

    rights_factor = 1.0
    details = []
    for criterion, selection in selections.items():
        index = CRITERION_OPTIONS[criterion].index(selection)
        coefficient = COEFFICIENTS[criterion][index]
        rights_factor *= coefficient
        details.append((criterion, selection, coefficient))

    calculated_rights = base_rights * rights_factor
    rights = max(MINIMUM_RIGHTS, calculated_rights) if base_rights > 0 else 0.0
    minimum_applied = base_rights > 0 and calculated_rights < MINIMUM_RIGHTS

    subtotal_before_margin = creative_cost + urgency_amount + rights + expenses
    margin_amount = subtotal_before_margin * margin_pct / 100
    before_discount = subtotal_before_margin + margin_amount
    discount_amount = before_discount * discount_pct / 100
    total = max(0.0, before_discount - discount_amount)

    return {
        "preparation": preparation,
        "production": production,
        "postproduction": postproduction,
        "creative_cost": creative_cost,
        "importance_label": importance_label,
        "importance_rate": importance_rate,
        "urgency_label": urgency_label,
        "urgency_rate": urgency_rate,
        "urgency_amount": urgency_amount,
        "base_rights": base_rights,
        "rights_factor": rights_factor,
        "calculated_rights": calculated_rights,
        "rights": rights,
        "minimum_applied": minimum_applied,
        "expenses": expenses,
        "subtotal_before_margin": subtotal_before_margin,
        "margin_pct": margin_pct,
        "margin_amount": margin_amount,
        "discount_pct": discount_pct,
        "discount_amount": discount_amount,
        "total": total,
        "details": details,
    }


def build_quote_html(client, project, pricing, notes, validity):
    rows = "".join(
        f"<tr><td>{escape(criterion)}</td><td>{escape(choice)}</td><td>{coefficient:.2f}</td></tr>"
        for criterion, choice, coefficient in pricing["details"]
    )
    return f"""<!doctype html>
<html lang='fr'><head><meta charset='utf-8'><title>Devis {escape(project)}</title>
<style>
body{{font-family:Arial,sans-serif;color:#21313D;margin:40px}}
h1{{color:#18354A}}.box{{background:#EAF7F5;padding:16px;border-radius:10px}}
table{{border-collapse:collapse;width:100%;margin:18px 0}}
th,td{{border:1px solid #DDE6EA;padding:9px;text-align:left}}
th{{background:#18354A;color:white}}.total{{font-size:22px;color:#0B7E76;font-weight:700}}
small{{color:#65727A}}@media print{{body{{margin:15mm}}}}
</style></head><body>
<h1>DEVIS INDICATIF</h1>
<div class='box'><b>Client :</b> {escape(client)}<br><b>Projet :</b> {escape(project)}<br>
<b>Date :</b> {datetime.now().strftime('%d/%m/%Y')}<br><b>Validité :</b> {validity} jours</div>
<h2>Détail financier</h2>
<table><tr><th>Poste</th><th>Montant HT</th></tr>
<tr><td>Préparation</td><td>{euro(pricing['preparation'])}</td></tr>
<tr><td>Production</td><td>{euro(pricing['production'])}</td></tr>
<tr><td>Postproduction</td><td>{euro(pricing['postproduction'])}</td></tr>
<tr><td>Majoration urgence</td><td>{euro(pricing['urgency_amount'])}</td></tr>
<tr><td>Droits d'utilisation</td><td>{euro(pricing['rights'])}</td></tr>
<tr><td>Frais</td><td>{euro(pricing['expenses'])}</td></tr>
<tr><td>Marge / honoraires ({pricing['margin_pct']:.0f} %)</td><td>{euro(pricing['margin_amount'])}</td></tr>
<tr><td>Remise</td><td>- {euro(pricing['discount_amount'])}</td></tr></table>
<p class='total'>Total HT : {euro(pricing['total'])}</p>
<h2>Paramètres des droits</h2>
<p><b>Importance du rendu :</b> {escape(pricing['importance_label'])}<br>
<b>Urgence :</b> {escape(pricing['urgency_label'])}<br>
<b>Base de droits :</b> {euro(pricing['base_rights'])}</p>
<table><tr><th>Critère</th><th>Choix</th><th>Coefficient</th></tr>{rows}</table>
<h2>Notes et conditions</h2><p>{escape(notes).replace(chr(10), '<br>')}</p>
<small>Document de travail à valider avant envoi. Les coefficients constituent une aide à la tarification et ne remplacent pas une analyse juridique ou fiscale adaptée.</small>
</body></html>"""


def build_brief_questions_prompt(brief):
    professions = ", ".join(brief.get("professions", [])) or "Non renseignées"
    return f"""Tu agis comme un directeur de production et business manager spécialisé dans les missions créatives.

Ta mission est de préparer une liste exhaustive, structurée et priorisée de questions à poser au client afin de transformer les informations ci-dessous en brief opérationnel, commercial et contractuel complet.

INFORMATIONS DÉJÀ CONNUES
- Client : {brief.get('client') or 'Non renseigné'}
- Projet : {brief.get('title') or 'Non renseigné'}
- Métier(s) nécessaire(s) : {professions}
- Compétences / style recherchés : {brief.get('skills') or 'Non renseignés'}
- Budget ou plafond HT : {euro(brief.get('budget', 0))}
- Lieu / zone : {brief.get('location') or 'Non renseigné'}
- Description actuelle : {brief.get('description') or 'Non renseignée'}

OBJECTIF
Produire uniquement les questions encore utiles. Ne repose pas une information déjà clairement fournie, sauf si une précision est indispensable. Utilise un langage naturel que je peux reprendre directement lors d'un rendez-vous client.

ORGANISE LES QUESTIONS DANS LES RUBRIQUES SUIVANTES
1. Contexte de l'entreprise, de la marque et du projet.
2. Objectif business, objectif de communication et résultat attendu.
3. Public cible, audience, marchés et comportement recherché.
4. Message principal, arguments, ton, émotion et perception voulue.
5. Références visuelles, univers souhaité, contre-exemples et charte existante.
6. Livrables exacts : nombre, formats, dimensions, durée, langues, déclinaisons et fichiers sources.
7. Préparation : repérage, script, storyboard, casting, intervenants, stylisme, maquillage, accessoires et autorisations.
8. Production : date, horaires, lieu, accès, interlocuteurs, matériel, logistique, sécurité et contraintes techniques.
9. Postproduction : retouche, montage, sound design, sous-titrage, étalonnage, formats de livraison et archivage.
10. Planning : date impérative, jalons, validations, niveau d'urgence et conséquences d'un retard client.
11. Gouvernance : décideur final, participants aux retours, processus de validation et délai d'acceptation.
12. Retours : nombre d'allers-retours inclus, nature des corrections et traitement des demandes hors périmètre.
13. Budget : enveloppe, frais inclus ou non, acompte, facturation, délai de paiement et budget média éventuel.
14. Droits d'utilisation : droits concernés, supports, finalités, diffusion, tirage ou audience, territoire, durée et exclusivité.
15. Adaptation et réutilisation : modifications, traduction, recadrage, sous-licence, rétrocession et exploitation par des partenaires.
16. Droit à l'image et droits de tiers : personnes, lieux, marques, musiques, œuvres, autorisations et responsabilités.
17. Portfolio et crédit : droit de montrer le projet, date de publication, confidentialité, mention du talent et anonymat.
18. Annulation, report, force majeure, météo, indisponibilité, frais engagés et indemnité d'immobilisation.
19. Contrat : documents applicables, ordre de priorité, propriété des fichiers sources, responsabilité, assurance, résiliation et juridiction.
20. Critères de réussite : indicateurs, méthode d'évaluation et définition précise d'un livrable accepté.

FORMAT ATTENDU
A. Commence par les 12 questions indispensables à poser en priorité.
B. Ajoute ensuite les questions complémentaires classées par rubrique.
C. Termine par une liste des pièces à demander au client avant devis ou démarrage.
D. Termine par les zones de risque ou informations critiques encore absentes.
E. N'invente aucune réponse à la place du client.
"""


def build_contract_prompt(context):
    pricing = context.get("pricing", {})
    selections = context.get("selections", {})
    rights_lines = "\n".join(f"- {key} : {value}" for key, value in selections.items())
    return f"""Tu agis comme assistant de revue contractuelle pour une prestation créative en France.

OBJECTIF
Comparer le contrat reçu avec les paramètres commerciaux convenus ci-dessous. Identifier les clauses conformes, absentes, ambiguës, plus larges que prévu ou défavorables au prestataire. Ne pas inventer le contenu manquant. Citer les passages pertinents et leur article lorsqu'il est disponible.

IMPORTANT
Cette analyse est une aide opérationnelle et ne remplace pas un avis juridique. Distingue les faits, les risques et les recommandations. Signale les points nécessitant la validation d'un professionnel du droit.

PARAMÈTRES COMMERCIAUX
- Importance du rendu : {context.get('importance')}
- Urgence : {context.get('urgency')}
- Préparation : {euro(pricing.get('preparation'))}
- Production : {euro(pricing.get('production'))}
- Postproduction : {euro(pricing.get('postproduction'))}
- Majoration urgence : {euro(pricing.get('urgency_amount'))}
- Base de droits : {euro(pricing.get('base_rights'))}
- Droits facturés : {euro(pricing.get('rights'))}
- Frais : {euro(pricing.get('expenses'))}
- Marge / honoraires : {euro(pricing.get('margin_amount'))}
- Remise : {euro(pricing.get('discount_amount'))}
- Total HT : {euro(pricing.get('total'))}

PÉRIMÈTRE DES DROITS
{rights_lines}

CONTRÔLES OBLIGATOIRES
Identité des parties, périmètre, livrables, planning, urgence, prix, acompte, paiement, retours, acceptation, supports, finalités, diffusion, territoire, durée, exclusivité, adaptation, traduction, modification, sous-licence, rétrocession, condition de paiement complet, crédit, droit moral, droit à l'image, droits de tiers, annulation, report, force majeure, responsabilité, assurance, garantie d'éviction, confidentialité, portfolio, fichiers sources, sous-traitance, résiliation, droit applicable, juridiction et ordre de priorité des documents.

FORMAT ATTENDU
1. Résumé exécutif.
2. Tableau : Critère | Attendu | Clause trouvée | Statut | Risque | Action recommandée.
3. Clauses à négocier en priorité.
4. Proposition de rédaction corrective.
5. Questions à poser avant signature.
6. Conclusion factuelle : signer en l'état, clarifier, négocier ou transmettre à un professionnel du droit.

CONTRAT À ANALYSER
COLLER ICI LE TEXTE INTÉGRAL DU CONTRAT
"""


st.markdown(
    "<div class='main-title'><h1>🎨 Manager business de créatifs</h1>"
    "<p>Qualification des missions, tarification, devis et sécurisation contractuelle.</p></div>",
    unsafe_allow_html=True,
)

tabs = st.tabs([
    "Briefs",
    "Simulateur",
    "Devis",
    "Suivi",
    "Analyse contrat IA",
    "Sauvegarde",
])

with tabs[0]:
    st.header("Briefs de mission")
    with st.form("brief_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        client = c1.text_input("Client *")
        title = c2.text_input("Nom du projet *")
        professions = c1.multiselect("Métier(s) nécessaire(s)", PROFESSIONS)
        skills = c2.text_area("Compétences / style recherchés")
        budget = c1.number_input("Budget ou plafond HT (€)", min_value=0.0, step=100.0)
        location = c2.text_input("Lieu / zone")
        description = st.text_area("Description du besoin")
        if st.form_submit_button("Créer le brief"):
            if not client or not title:
                st.error("Le client et le nom du projet sont obligatoires.")
            else:
                st.session_state.briefs.append({
                    "id": datetime.now().timestamp(),
                    "client": client,
                    "title": title,
                    "professions": professions,
                    "skills": skills,
                    "budget": budget,
                    "location": location,
                    "description": description,
                })
                st.success("Brief créé.")

    if st.session_state.briefs:
        st.subheader("Briefs enregistrés")
        for index, brief in enumerate(st.session_state.briefs):
            with st.expander(f"{brief['client']} · {brief['title']}"):
                st.write(brief)
                if st.button("Supprimer", key=f"delete_brief_{index}"):
                    st.session_state.briefs.pop(index)
                    st.rerun()

        st.divider()
        st.subheader("Prompt IA pour préparer toutes les questions client")
        brief_index = st.selectbox(
            "Brief à approfondir",
            range(len(st.session_state.briefs)),
            format_func=lambda i: f"{st.session_state.briefs[i]['client']} · {st.session_state.briefs[i]['title']}",
        )
        selected_brief = st.session_state.briefs[brief_index]
        brief_prompt = build_brief_questions_prompt(selected_brief)
        st.text_area("Prompt prêt à copier", value=brief_prompt, height=600)
        st.download_button(
            "Télécharger le prompt de qualification",
            brief_prompt,
            "prompt_questions_brief_client.txt",
            "text/plain",
        )
    else:
        st.info("Crée un brief pour générer automatiquement le questionnaire client.")

with tabs[1]:
    st.header("Simulateur de tarification")
    st.write(
        "Renseigne les heures de préparation, de production et de postproduction, "
        "puis déplace les curseurs selon l'exploitation prévue."
    )

    st.subheader("Temps de travail")
    c1, c2, c3 = st.columns(3)
    preparation_hours = c1.number_input("Heures de préparation", min_value=0.0, value=2.0, step=0.5)
    production_hours = c2.number_input("Heures de production", min_value=0.0, value=8.0, step=0.5)
    postproduction_hours = c3.number_input("Heures de postproduction", min_value=0.0, value=3.0, step=0.5)

    c1, c2, c3 = st.columns(3)
    preparation_rate = c1.number_input("Tarif préparation / heure HT (€)", min_value=0.0, value=50.0, step=10.0)
    production_rate = c2.number_input("Tarif production / heure HT (€)", min_value=0.0, value=75.0, step=10.0)
    postproduction_rate = c3.number_input("Tarif postproduction / heure HT (€)", min_value=0.0, value=60.0, step=10.0)

    st.subheader("Valeur du rendu et urgence")
    importance_label = st.select_slider(
        "Importance intrinsèque du rendu",
        options=list(IMPORTANCE_OPTIONS.keys()),
        value="Création centrale · 60 %",
    )
    urgency_label = st.select_slider(
        "Niveau d'urgence",
        options=list(URGENCY_OPTIONS.keys()),
        value="Planning normal · 0 %",
    )
    st.caption(
        "La base de droits est calculée automatiquement : coût créatif × importance du rendu. "
        "L'urgence majore le coût créatif, pas les droits."
    )

    st.subheader("Étendue des droits d'utilisation")
    selections = {}
    for criterion, options in CRITERION_OPTIONS.items():
        selection = st.select_slider(
            criterion,
            options=options,
            value=options[len(options) // 2],
            key=f"slider_{criterion}",
        )
        selections[criterion] = selection
        index = options.index(selection)
        st.caption(f"Choix retenu : {selection} · coefficient {COEFFICIENTS[criterion][index]:.2f}")

    st.subheader("Frais et ajustements")
    c1, c2, c3 = st.columns(3)
    expenses = c1.number_input("Frais techniques et déplacements HT (€)", min_value=0.0, value=0.0, step=25.0)
    margin_pct = c2.number_input("Marge / honoraires (%)", min_value=0.0, max_value=100.0, value=10.0, step=1.0)
    discount_pct = c3.number_input("Remise commerciale (%)", min_value=0.0, max_value=100.0, value=0.0, step=1.0)

    pricing = compute_price(
        preparation_hours,
        production_hours,
        postproduction_hours,
        preparation_rate,
        production_rate,
        postproduction_rate,
        importance_label,
        urgency_label,
        selections,
        expenses,
        margin_pct,
        discount_pct,
    )
    st.session_state.last_pricing = pricing
    st.session_state.last_context = {
        "importance": importance_label,
        "urgency": urgency_label,
        "selections": selections,
        "pricing": pricing,
    }

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Coût créatif", euro(pricing["creative_cost"]))
    m2.metric("Base de droits", euro(pricing["base_rights"]))
    m3.metric("Urgence", euro(pricing["urgency_amount"]))
    m4.metric("Droits", euro(pricing["rights"]))
    m5.metric("Marge", euro(pricing["margin_amount"]), f"{pricing['margin_pct']:.0f} %")
    m6.metric("Total HT", euro(pricing["total"]))

    st.markdown(
        f"""<div class='card'><b>Détail de la marge</b><br>
        Assiette avant marge : {euro(pricing['subtotal_before_margin'])}<br>
        Taux de marge / honoraires : {pricing['margin_pct']:.0f} %<br>
        <b>Montant de la marge : {euro(pricing['margin_amount'])}</b></div>""",
        unsafe_allow_html=True,
    )

    if pricing["minimum_applied"]:
        st.info(f"Le minimum de droits de {euro(MINIMUM_RIGHTS)} a été appliqué.")

    st.dataframe(
        [
            {"Critère": criterion, "Choix": choice, "Coefficient": coefficient}
            for criterion, choice, coefficient in pricing["details"]
        ],
        use_container_width=True,
        hide_index=True,
    )

with tabs[2]:
    st.header("Générer un devis")
    pricing = st.session_state.last_pricing
    if not pricing:
        st.info("Calcule d'abord un tarif dans le simulateur.")
    else:
        client_default = st.session_state.briefs[-1]["client"] if st.session_state.briefs else ""
        project_default = st.session_state.briefs[-1]["title"] if st.session_state.briefs else ""
        client = st.text_input("Client", value=client_default, key="quote_client")
        project = st.text_input("Projet", value=project_default, key="quote_project")
        validity = st.number_input("Validité du devis en jours", min_value=1, value=30)
        notes = st.text_area(
            "Notes / conditions",
            value="Acompte, planning, livrables, retours et périmètre des droits à confirmer avant démarrage.",
        )
        quote_html = build_quote_html(client, project, pricing, notes, validity)
        filename = re.sub(r"[^a-zA-Z0-9]+", "_", project or "projet").strip("_")
        st.download_button(
            "Télécharger le devis HTML",
            quote_html.encode("utf-8"),
            file_name=f"devis_{filename}.html",
            mime="text/html",
        )
        st.caption("Ouvre le fichier dans un navigateur puis utilise Imprimer → Enregistrer au format PDF.")

with tabs[3]:
    st.header("Suivi des opportunités")
    with st.form("opportunity_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        opp_client = c1.text_input("Client")
        opp_project = c2.text_input("Projet")
        opp_status = c3.selectbox(
            "Statut",
            ["À qualifier", "Devis à préparer", "Devis envoyé", "Relance", "Gagné", "Perdu"],
        )
        opp_amount = c1.number_input("Montant HT (€)", min_value=0.0, step=100.0)
        opp_next = c2.text_input("Prochaine action")
        opp_notes = c3.text_input("Notes")
        if st.form_submit_button("Ajouter au suivi"):
            st.session_state.opportunities.append({
                "client": opp_client,
                "project": opp_project,
                "status": opp_status,
                "amount": opp_amount,
                "next_action": opp_next,
                "notes": opp_notes,
            })
            st.success("Opportunité ajoutée.")
    st.dataframe(st.session_state.opportunities, use_container_width=True, hide_index=True)

with tabs[4]:
    st.header("Prompt d'analyse du contrat avec une IA")
    st.warning(
        "Ce prompt aide à repérer les écarts entre le contrat et les paramètres commerciaux. "
        "Il ne remplace pas la validation d'un avocat ou d'un professionnel du droit."
    )
    context = st.session_state.last_context
    if not context:
        st.info("Effectue d'abord une simulation tarifaire pour préremplir les critères.")
    else:
        contract_prompt = build_contract_prompt(context)
        st.text_area("Prompt prêt à copier", value=contract_prompt, height=650)
        st.download_button(
            "Télécharger le prompt d'analyse contractuelle",
            contract_prompt,
            "prompt_analyse_contrat_creatif.txt",
            "text/plain",
        )

with tabs[5]:
    st.header("Sauvegarde et restauration")
    export_data = {
        "version": 5,
        "exported_at": datetime.now().isoformat(),
        "briefs": st.session_state.briefs,
        "opportunities": st.session_state.opportunities,
    }
    st.download_button(
        "Télécharger la sauvegarde JSON",
        json.dumps(export_data, ensure_ascii=False, indent=2),
        "manager_creatifs_sauvegarde.json",
        "application/json",
    )
    uploaded = st.file_uploader("Restaurer une sauvegarde JSON", type=["json"])
    if uploaded and st.button("Restaurer les données"):
        try:
            data = json.loads(uploaded.getvalue().decode("utf-8-sig"))
            st.session_state.briefs = data.get("briefs", [])
            st.session_state.opportunities = data.get("opportunities", [])
            st.success("Données restaurées.")
            st.rerun()
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as error:
            st.error(f"Sauvegarde invalide : {error}")
