import json
import re
from datetime import date, datetime
from html import escape

import streamlit as st

st.set_page_config(page_title="Manager de créatifs", page_icon="🎨", layout="wide")

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.6rem; padding-bottom: 4rem;}
    .hero {padding: 25px; border-radius: 18px; color: white;
        background: linear-gradient(135deg,#18354D,#25647A); margin-bottom: 20px;}
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
        "selected_brief_id": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_state()


def euro(value):
    return f"{float(value or 0):,.2f} €".replace(",", " ").replace(".", ",")


def format_date(value):
    if not value:
        return "Non renseignée"
    if isinstance(value, str):
        return value
    return value.strftime("%d/%m/%Y")


def budget_summary(brief):
    mode = brief.get("budget_mode", "Budget à confirmer")
    if mode == "Le client a une enveloppe précise":
        return f"{mode} : {euro(brief.get('budget_exact', 0))}"
    if mode == "Le client a une fourchette budgétaire":
        return f"{mode} : {euro(brief.get('budget_min', 0))} à {euro(brief.get('budget_max', 0))}"
    return mode


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
        "urgency_label": urgency_label,
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
    return f"""<!doctype html><html lang='fr'><head><meta charset='utf-8'>
<title>Devis {escape(project)}</title><style>
body{{font-family:Arial,sans-serif;color:#21313D;margin:40px}}h1{{color:#18354A}}
.box{{background:#EAF7F5;padding:16px;border-radius:10px}}table{{border-collapse:collapse;width:100%;margin:18px 0}}
th,td{{border:1px solid #DDE6EA;padding:9px;text-align:left}}th{{background:#18354A;color:white}}
.total{{font-size:22px;color:#0B7E76;font-weight:700}}small{{color:#65727A}}@media print{{body{{margin:15mm}}}}
</style></head><body><h1>DEVIS INDICATIF</h1>
<div class='box'><b>Client :</b> {escape(client)}<br><b>Projet :</b> {escape(project)}<br>
<b>Date :</b> {datetime.now().strftime('%d/%m/%Y')}<br><b>Validité :</b> {validity} jours</div>
<h2>Détail financier</h2><table><tr><th>Poste</th><th>Montant HT</th></tr>
<tr><td>Préparation</td><td>{euro(pricing['preparation'])}</td></tr>
<tr><td>Production</td><td>{euro(pricing['production'])}</td></tr>
<tr><td>Postproduction</td><td>{euro(pricing['postproduction'])}</td></tr>
<tr><td>Majoration urgence</td><td>{euro(pricing['urgency_amount'])}</td></tr>
<tr><td>Droits d'utilisation</td><td>{euro(pricing['rights'])}</td></tr>
<tr><td>Frais</td><td>{euro(pricing['expenses'])}</td></tr>
<tr><td>Marge / honoraires ({pricing['margin_pct']:.0f} %)</td><td>{euro(pricing['margin_amount'])}</td></tr>
<tr><td>Remise</td><td>- {euro(pricing['discount_amount'])}</td></tr></table>
<p class='total'>Total HT : {euro(pricing['total'])}</p>
<h2>Paramètres des droits</h2><p><b>Importance du rendu :</b> {escape(pricing['importance_label'])}<br>
<b>Urgence :</b> {escape(pricing['urgency_label'])}<br><b>Base de droits :</b> {euro(pricing['base_rights'])}</p>
<table><tr><th>Critère</th><th>Choix</th><th>Coefficient</th></tr>{rows}</table>
<h2>Notes et conditions</h2><p>{escape(notes).replace(chr(10), '<br>')}</p>
<small>Document de travail à valider avant envoi. Les coefficients constituent une aide à la tarification.</small>
</body></html>"""


def build_brief_questions_prompt(brief):
    professions = ", ".join(brief.get("professions", [])) or "Non renseignés"
    return f"""Tu agis comme directeur de production et business manager spécialisé dans les missions créatives.

OBJECTIF
À partir des informations déjà connues, produire une liste exhaustive, structurée et priorisée des questions encore nécessaires pour rendre le brief opérationnel, commercial et contractuel. Ne repose pas une question dont la réponse est déjà claire. N'invente aucune réponse.

INFORMATIONS DÉJÀ CONNUES
- Client : {brief.get('client') or 'Non renseigné'}
- Contact principal : {brief.get('contact_name') or 'Non renseigné'}
- Fonction du contact : {brief.get('contact_role') or 'Non renseignée'}
- Projet : {brief.get('title') or 'Non renseigné'}
- Type de projet : {brief.get('project_type') or 'Non renseigné'}
- Nombre de profils recherchés : {brief.get('profile_count') or 'Non renseigné'}
- Métiers nécessaires : {professions}
- Un même profil peut-il couvrir plusieurs métiers : {brief.get('multi_role_allowed') or 'Non renseigné'}
- Démarrage souhaité : {format_date(brief.get('start_date'))}
- Date de production / intervention : {format_date(brief.get('production_date'))}
- Date de livraison finale : {format_date(brief.get('delivery_date'))}
- Budget : {budget_summary(brief)}
- Lieu : {brief.get('location') or 'Non renseigné'}
- Télétravail / présence : {brief.get('work_mode') or 'Non renseigné'}
- Objectif business : {brief.get('business_goal') or 'Non renseigné'}
- Public cible : {brief.get('target_audience') or 'Non renseigné'}
- Message principal : {brief.get('key_message') or 'Non renseigné'}
- Livrables connus : {brief.get('deliverables') or 'Non renseignés'}
- Compétences / style : {brief.get('skills') or 'Non renseignés'}
- Références ou inspirations : {brief.get('references') or 'Non renseignées'}
- Contraintes connues : {brief.get('constraints') or 'Non renseignées'}
- Matériel / ressources fournis par le client : {brief.get('client_inputs') or 'Non renseignés'}
- Processus de validation : {brief.get('approval_process') or 'Non renseigné'}
- Nombre de retours souhaité : {brief.get('revision_rounds') or 'Non renseigné'}
- Utilisations envisagées : {brief.get('usage_notes') or 'Non renseignées'}
- Informations complémentaires : {brief.get('description') or 'Non renseignées'}

TRAITEMENT SPÉCIFIQUE DU BUDGET
- Si le client attend notre estimation, ne lui demande pas immédiatement « quel est votre budget ? ».
- Pose plutôt des questions permettant le chiffrage : niveau d'ambition, livrables indispensables et optionnels, volume, qualité attendue, planning, nombre de profils, matériel, déplacements, postproduction, retours et droits d'utilisation.
- Propose ensuite trois scénarios à chiffrer : essentiel, recommandé et premium.
- Si le client a une enveloppe ou une fourchette, vérifie ce qu'elle inclut : production, talents, matériel, frais, droits, marge, taxes et achat média.

RUBRIQUES À COUVRIR
1. Contexte, objectifs business et critères de réussite.
2. Cible, message, ton et action attendue du public.
3. Composition de l'équipe : nombre de profils, rôles, cumul de fonctions, séniorité et disponibilités.
4. Livrables : quantité, formats, dimensions, durée, langues, déclinaisons, fichiers sources et rushes.
5. Préparation : réunion de cadrage, repérage, script, storyboard, casting, planning, stylisme, maquillage, accessoires.
6. Production : dates, horaires, lieu, accès, autorisations, sécurité, matériel, équipe client, logistique et météo.
7. Postproduction : montage, retouche, étalonnage, sous-titrage, son, versions, archivage et livraison.
8. Planning : jalons, dépendances, validation, urgence réelle et conséquences des retards imputables au client.
9. Gouvernance : contact opérationnel, décideur final, approbateurs, consolidation des retours et délai d'acceptation.
10. Révisions : nombre d'allers-retours, corrections incluses, changement de brief et procédure de chiffrage complémentaire.
11. Budget et estimation : hypothèses, inclusions, exclusions, options, acompte, facturation et délai de paiement.
12. Droits : supports, finalités, diffusion, tirage, audience, territoire, durée, exclusivité, adaptation, modification et partenaires.
13. Droits de tiers : droit à l'image, lieux, marques, musiques, œuvres, licences et personne responsable des autorisations.
14. Portfolio, crédit, confidentialité, embargo et date de communication.
15. Annulation, report, force majeure, météo, frais engagés et indemnité d'immobilisation.
16. Contrat : documents applicables, ordre de priorité, responsabilité, assurance, propriété des sources, résiliation et juridiction.
17. Éléments fournis par le client : charte, logos, textes, produits, accès, données, plans, contacts et dates de remise.
18. Accessibilité, conformité, RSE, sécurité, RGPD et exigences spécifiques au secteur.

FORMAT ATTENDU
A. Les 15 questions indispensables à poser en priorité.
B. Les questions complémentaires, classées par rubrique.
C. Les questions spécifiques au métier ou aux métiers sélectionnés.
D. Les pièces et accès à demander avant devis.
E. Les hypothèses nécessaires pour produire une estimation si le budget est inconnu.
F. Trois scénarios de cadrage à chiffrer : essentiel, recommandé et premium, sans inventer de prix.
G. Les zones de risque et les informations bloquantes avant engagement.
"""


def build_contract_prompt(context):
    pricing = context.get("pricing", {})
    selections = context.get("selections", {})
    rights_lines = "\n".join(f"- {key} : {value}" for key, value in selections.items())
    return f"""Tu agis comme assistant de revue contractuelle pour une prestation créative en France.

OBJECTIF
Comparer le contrat reçu avec les paramètres commerciaux convenus. Identifier les clauses conformes, absentes, ambiguës, plus larges que prévu ou défavorables au prestataire. Cite les passages pertinents et leurs articles. N'invente rien.

IMPORTANT
Cette analyse est une aide opérationnelle et ne remplace pas un avis juridique. Distingue les faits, risques et recommandations.

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
Identité des parties, périmètre, nombre de profils, rôles cumulés, livrables, dates, planning, urgence, prix, acompte, paiement, retours, acceptation, supports, diffusion, territoire, durée, exclusivité, adaptation, traduction, sous-licence, rétrocession, condition de paiement complet, crédit, droit moral, droit à l'image, droits de tiers, annulation, report, responsabilité, assurance, confidentialité, portfolio, fichiers sources, sous-traitance, résiliation, droit applicable, juridiction et ordre de priorité des documents.

FORMAT
1. Résumé exécutif.
2. Tableau : Critère | Attendu | Clause trouvée | Statut | Risque | Action.
3. Clauses à négocier.
4. Rédactions correctives.
5. Questions avant signature.
6. Conclusion : signer, clarifier, négocier ou transmettre à un professionnel du droit.

CONTRAT À ANALYSER
COLLER ICI LE TEXTE INTÉGRAL DU CONTRAT
"""


st.markdown(
    "<div class='hero'><h1>🎨 Manager business de créatifs</h1>"
    "<p>Qualification complète, estimation, devis et sécurisation contractuelle.</p></div>",
    unsafe_allow_html=True,
)

tabs = st.tabs(["Briefs", "Simulateur", "Devis", "Suivi", "Analyse contrat IA", "Sauvegarde"])

with tabs[0]:
    st.header("Briefs de mission")
    with st.form("brief_form", clear_on_submit=True):
        st.subheader("1. Identification")
        c1, c2, c3 = st.columns(3)
        client = c1.text_input("Client *")
        contact_name = c2.text_input("Contact principal")
        contact_role = c3.text_input("Fonction du contact")
        title = c1.text_input("Nom du projet *")
        project_type = c2.selectbox(
            "Type de projet",
            ["À préciser", "Photo", "Vidéo", "Graphisme", "Motion design", "Contenu social", "Événement", "Campagne", "Autre"],
        )
        profile_count = c3.number_input("Nombre de profils recherchés", min_value=1, value=1, step=1)
        professions = st.multiselect("Métier(s) nécessaire(s)", PROFESSIONS)
        multi_role_allowed = st.radio(
            "Un même profil peut-il couvrir plusieurs métiers ?",
            ["Oui", "Non", "À confirmer"],
            horizontal=True,
        )

        st.subheader("2. Dates et organisation")
        c1, c2, c3 = st.columns(3)
        start_date_known = c1.checkbox("Date de démarrage connue")
        production_date_known = c2.checkbox("Date de production connue")
        delivery_date_known = c3.checkbox("Date de livraison connue")
        start_date = c1.date_input("Démarrage souhaité", value=date.today()) if start_date_known else None
        production_date = c2.date_input("Production / intervention", value=date.today()) if production_date_known else None
        delivery_date = c3.date_input("Livraison finale", value=date.today()) if delivery_date_known else None
        c1, c2, c3 = st.columns(3)
        location = c1.text_input("Lieu / zone")
        work_mode = c2.selectbox("Modalité", ["Sur site", "À distance", "Hybride", "À confirmer"])
        urgency_known = c3.selectbox("Niveau d'urgence perçu", ["Normal", "Resserré", "Urgent", "Très urgent", "À confirmer"])

        st.subheader("3. Besoin et résultat attendu")
        business_goal = st.text_area("Objectif business ou communication")
        target_audience = st.text_area("Public cible")
        key_message = st.text_area("Message principal / action attendue")
        deliverables = st.text_area("Livrables déjà identifiés")
        skills = st.text_area("Compétences, style, logiciels ou expérience nécessaires")
        references = st.text_area("Références, inspirations et contre-exemples")

        st.subheader("4. Budget")
        budget_mode = st.selectbox("Situation budgétaire", BUDGET_MODES)
        c1, c2 = st.columns(2)
        budget_exact = 0.0
        budget_min = 0.0
        budget_max = 0.0
        if budget_mode == "Le client a une enveloppe précise":
            budget_exact = c1.number_input("Enveloppe précise HT (€)", min_value=0.0, step=100.0)
        elif budget_mode == "Le client a une fourchette budgétaire":
            budget_min = c1.number_input("Budget minimum HT (€)", min_value=0.0, step=100.0)
            budget_max = c2.number_input("Budget maximum HT (€)", min_value=0.0, step=100.0)
        elif budget_mode == "Le client attend notre estimation":
            st.info("Le prompt de qualification demandera les hypothèses nécessaires pour construire des scénarios essentiel, recommandé et premium.")
        budget_includes = st.multiselect(
            "Ce que le budget semble inclure",
            ["Préparation", "Production", "Postproduction", "Talents", "Matériel", "Déplacements", "Droits", "Marge", "Taxes", "Achat média", "À confirmer"],
        )

        st.subheader("5. Validation, contraintes et droits")
        c1, c2 = st.columns(2)
        approval_process = c1.text_area("Décideur final et processus de validation")
        revision_rounds = c2.selectbox("Nombre d'allers-retours envisagé", ["À confirmer", "1", "2", "3", "Plus de 3"])
        constraints = c1.text_area("Contraintes techniques, légales, sécurité, RSE ou accessibilité")
        client_inputs = c2.text_area("Éléments et ressources fournis par le client")
        usage_notes = st.text_area("Utilisations, supports, diffusion, territoire, durée et exclusivité déjà envisagés")
        description = st.text_area("Informations complémentaires")

        if st.form_submit_button("Créer le brief"):
            if not client or not title:
                st.error("Le client et le nom du projet sont obligatoires.")
            elif budget_mode == "Le client a une fourchette budgétaire" and budget_max and budget_min > budget_max:
                st.error("Le budget minimum ne peut pas dépasser le budget maximum.")
            else:
                brief = {
                    "id": datetime.now().timestamp(),
                    "client": client,
                    "contact_name": contact_name,
                    "contact_role": contact_role,
                    "title": title,
                    "project_type": project_type,
                    "profile_count": int(profile_count),
                    "professions": professions,
                    "multi_role_allowed": multi_role_allowed,
                    "start_date": start_date.isoformat() if start_date else None,
                    "production_date": production_date.isoformat() if production_date else None,
                    "delivery_date": delivery_date.isoformat() if delivery_date else None,
                    "location": location,
                    "work_mode": work_mode,
                    "urgency_known": urgency_known,
                    "business_goal": business_goal,
                    "target_audience": target_audience,
                    "key_message": key_message,
                    "deliverables": deliverables,
                    "skills": skills,
                    "references": references,
                    "budget_mode": budget_mode,
                    "budget_exact": budget_exact,
                    "budget_min": budget_min,
                    "budget_max": budget_max,
                    "budget_includes": budget_includes,
                    "approval_process": approval_process,
                    "revision_rounds": revision_rounds,
                    "constraints": constraints,
                    "client_inputs": client_inputs,
                    "usage_notes": usage_notes,
                    "description": description,
                }
                st.session_state.briefs.append(brief)
                st.session_state.selected_brief_id = brief["id"]
                st.success("Brief créé.")

    if st.session_state.briefs:
        st.subheader("Briefs enregistrés")
        for index, brief in enumerate(st.session_state.briefs):
            with st.expander(f"{brief['client']} · {brief['title']} · {brief.get('profile_count', 1)} profil(s)"):
                st.write("**Dates :**", format_date(brief.get("start_date")), "|", format_date(brief.get("production_date")), "|", format_date(brief.get("delivery_date")))
                st.write("**Budget :**", budget_summary(brief))
                st.write("**Métiers :**", ", ".join(brief.get("professions", [])) or "Non renseignés")
                st.write("**Livrables :**", brief.get("deliverables") or "Non renseignés")
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
        st.text_area("Prompt prêt à copier", value=brief_prompt, height=650)
        st.download_button("Télécharger le prompt de qualification", brief_prompt, "prompt_questions_brief_client.txt", "text/plain")
    else:
        st.info("Crée un brief pour générer automatiquement le questionnaire client.")

with tabs[1]:
    st.header("Simulateur de tarification")

    selected_brief = None
    if st.session_state.briefs:
        brief_idx = st.selectbox(
            "Brief associé à l'estimation",
            range(len(st.session_state.briefs)),
            format_func=lambda i: f"{st.session_state.briefs[i]['client']} · {st.session_state.briefs[i]['title']}",
        )
        selected_brief = st.session_state.briefs[brief_idx]
        st.info(f"Situation budgétaire du client : {budget_summary(selected_brief)}")

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
    importance_label = st.select_slider("Importance intrinsèque du rendu", options=list(IMPORTANCE_OPTIONS.keys()), value="Création centrale · 60 %")
    urgency_label = st.select_slider("Niveau d'urgence", options=list(URGENCY_OPTIONS.keys()), value="Planning normal · 0 %")

    st.subheader("Étendue des droits d'utilisation")
    selections = {}
    for criterion, options in CRITERION_OPTIONS.items():
        selection = st.select_slider(criterion, options=options, value=options[len(options) // 2], key=f"slider_{criterion}")
        selections[criterion] = selection
        index = options.index(selection)
        st.caption(f"Choix retenu : {selection} · coefficient {COEFFICIENTS[criterion][index]:.2f}")

    st.subheader("Frais et ajustements")
    c1, c2, c3 = st.columns(3)
    expenses = c1.number_input("Frais techniques et déplacements HT (€)", min_value=0.0, value=0.0, step=25.0)
    margin_pct = c2.number_input("Marge / honoraires (%)", min_value=0.0, max_value=100.0, value=10.0, step=1.0)
    discount_pct = c3.number_input("Remise commerciale (%)", min_value=0.0, max_value=100.0, value=0.0, step=1.0)

    pricing = compute_price(
        preparation_hours, production_hours, postproduction_hours,
        preparation_rate, production_rate, postproduction_rate,
        importance_label, urgency_label, selections, expenses, margin_pct, discount_pct,
    )
    st.session_state.last_pricing = pricing
    st.session_state.last_context = {
        "importance": importance_label,
        "urgency": urgency_label,
        "selections": selections,
        "pricing": pricing,
        "brief": selected_brief,
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
        Taux : {pricing['margin_pct']:.0f} %<br>
        <b>Montant de la marge : {euro(pricing['margin_amount'])}</b></div>""",
        unsafe_allow_html=True,
    )

    if selected_brief:
        mode = selected_brief.get("budget_mode")
        if mode == "Le client a une enveloppe précise" and selected_brief.get("budget_exact", 0):
            gap = selected_brief["budget_exact"] - pricing["total"]
            st.success(f"Estimation sous l'enveloppe de {euro(gap)}") if gap >= 0 else st.error(f"Estimation au-dessus de l'enveloppe de {euro(abs(gap))}")
        elif mode == "Le client a une fourchette budgétaire" and selected_brief.get("budget_max", 0):
            if pricing["total"] < selected_brief.get("budget_min", 0):
                st.info("L'estimation est sous la fourchette annoncée. Vérifie que tout le périmètre est inclus.")
            elif pricing["total"] <= selected_brief.get("budget_max", 0):
                st.success("L'estimation se situe dans la fourchette du client.")
            else:
                st.error(f"L'estimation dépasse le maximum de {euro(pricing['total'] - selected_brief['budget_max'])}.")
        elif mode == "Le client attend notre estimation":
            st.info("Cette estimation constitue la proposition de référence à présenter au client avec les hypothèses retenues.")

    if pricing["minimum_applied"]:
        st.info(f"Le minimum de droits de {euro(MINIMUM_RIGHTS)} a été appliqué.")

with tabs[2]:
    st.header("Générer un devis")
    pricing = st.session_state.last_pricing
    if not pricing:
        st.info("Calcule d'abord un tarif dans le simulateur.")
    else:
        linked_brief = st.session_state.last_context.get("brief") or {}
        client = st.text_input("Client", value=linked_brief.get("client", ""), key="quote_client")
        project = st.text_input("Projet", value=linked_brief.get("title", ""), key="quote_project")
        validity = st.number_input("Validité du devis en jours", min_value=1, value=30)
        notes = st.text_area("Notes / conditions", value="Acompte, planning, livrables, retours et périmètre des droits à confirmer avant démarrage.")
        quote_html = build_quote_html(client, project, pricing, notes, validity)
        filename = re.sub(r"[^a-zA-Z0-9]+", "_", project or "projet").strip("_")
        st.download_button("Télécharger le devis HTML", quote_html.encode("utf-8"), file_name=f"devis_{filename}.html", mime="text/html")
        st.caption("Ouvre le fichier dans un navigateur puis utilise Imprimer → Enregistrer au format PDF.")

with tabs[3]:
    st.header("Suivi des opportunités")
    with st.form("opportunity_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        opp_client = c1.text_input("Client")
        opp_project = c2.text_input("Projet")
        opp_status = c3.selectbox("Statut", ["À qualifier", "Estimation à préparer", "Devis envoyé", "Relance", "Gagné", "Perdu"])
        opp_amount = c1.number_input("Montant HT (€)", min_value=0.0, step=100.0)
        opp_next = c2.text_input("Prochaine action")
        opp_notes = c3.text_input("Notes")
        if st.form_submit_button("Ajouter au suivi"):
            st.session_state.opportunities.append({"client": opp_client, "project": opp_project, "status": opp_status, "amount": opp_amount, "next_action": opp_next, "notes": opp_notes})
            st.success("Opportunité ajoutée.")
    st.dataframe(st.session_state.opportunities, use_container_width=True, hide_index=True)

with tabs[4]:
    st.header("Prompt d'analyse du contrat avec une IA")
    st.warning("Ce prompt aide à repérer les écarts. Il ne remplace pas un avis juridique.")
    if not st.session_state.last_context:
        st.info("Effectue d'abord une simulation tarifaire.")
    else:
        contract_prompt = build_contract_prompt(st.session_state.last_context)
        st.text_area("Prompt prêt à copier", value=contract_prompt, height=650)
        st.download_button("Télécharger le prompt d'analyse contractuelle", contract_prompt, "prompt_analyse_contrat_creatif.txt", "text/plain")

with tabs[5]:
    st.header("Sauvegarde et restauration")
    export_data = {
        "version": 6,
        "exported_at": datetime.now().isoformat(),
        "briefs": st.session_state.briefs,
        "opportunities": st.session_state.opportunities,
    }
    st.download_button("Télécharger la sauvegarde JSON", json.dumps(export_data, ensure_ascii=False, indent=2), "manager_creatifs_sauvegarde.json", "application/json")
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
