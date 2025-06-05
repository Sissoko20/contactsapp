import streamlit as st
import vobject
import pandas as pd
import io
import time
from rapidfuzz import fuzz

st.set_page_config(page_title="Éditeur de Contacts VCF", layout="wide")
st.title("📇 Éditeur de contacts VCF")


# 🔧 Nettoyage des lignes problématiques (ex: PHOTO)
def clean_vcf_lines(file_content):
    lines = file_content.splitlines()
    clean_lines = []
    skip_mode = False
    for line in lines:
        if line.startswith("PHOTO") or line.startswith("LOGO"):
            skip_mode = True
            continue
        if skip_mode and not line.startswith(" "):  # Fin du bloc encodé
            skip_mode = False
        if not skip_mode:
            clean_lines.append(line)
    return "\n".join(clean_lines)


# 🔍 Parsing sécurisé
def parse_vcf(file_content, max_time=5):
    contacts = []
    start_time = time.time()
    try:
        for vcard in vobject.readComponents(file_content, ignoreUnreadable=True):
            if time.time() - start_time > max_time:
                st.warning("⏱️ Parsing interrompu pour éviter un long chargement.")
                break
            try:
                contact = {
                    "Full Name": getattr(vcard, 'fn', None).value if hasattr(vcard, 'fn') else "",
                    "Telephone": getattr(vcard, 'tel', None).value if hasattr(vcard, 'tel') else "",
                    "Email": getattr(vcard, 'email', None).value if hasattr(vcard, 'email') else ""
                }
                contacts.append(contact)
            except Exception:
                continue
    except Exception as e:
        st.error("❌ Erreur pendant le parsing du fichier VCF.")
        st.exception(e)
    return pd.DataFrame(contacts)


# 🎯 Détection de doublons
def detect_duplicates_fast(df, threshold_name=90, threshold_phone=85):
    seen = set()
    duplicates = []
    index_map = df.reset_index().to_dict(orient="records")

    for i in range(len(index_map)):
        a = index_map[i]
        name_a = a["Full Name"]
        phone_a = a["Telephone"]
        email_a = a["Email"]

        for j in range(i + 1, len(index_map)):
            b = index_map[j]
            if j in seen:
                continue

            name_b = b["Full Name"]
            phone_b = b["Telephone"]
            email_b = b["Email"]

            name_score = fuzz.token_sort_ratio(name_a, name_b)
            phone_score = fuzz.partial_ratio(phone_a, phone_b) if phone_a and phone_b else 0
            email_score = fuzz.partial_ratio(email_a, email_b) if email_a and email_b else 0

            is_same_name = name_score >= threshold_name
            is_similar_contact = phone_score >= threshold_phone or (email_a and email_b and email_score >= 90)

            if is_same_name and is_similar_contact:
                duplicates.append((a["index"], b["index"], name_score, max(phone_score, email_score)))
                seen.add(j)

    return duplicates, list(seen)


# 💾 Export
def export_to_vcf(df):
    output = io.StringIO()
    for _, row in df.iterrows():
        vcard = vobject.vCard()
        vcard.add('fn')
        vcard.fn.value = row['Full Name']
        if row['Telephone']:
            vcard.add('tel')
            vcard.tel.value = row['Telephone']
            vcard.tel.type_param = 'CELL'
        if row['Email']:
            vcard.add('email')
            vcard.email.value = row['Email']
            vcard.email.type_param = 'INTERNET'
        output.write(vcard.serialize())
    return output.getvalue()


# 📥 Upload fichier
uploaded_file = st.file_uploader("Importer un fichier .vcf", type=["vcf"])

if uploaded_file:
    try:
        file_content = uploaded_file.read().decode("utf-8", errors="ignore")
        st.info("📄 Fichier chargé. Analyse en cours...")

        cleaned_content = clean_vcf_lines(file_content)
        df = parse_vcf(cleaned_content).fillna("")

        if df.empty:
            st.warning("⚠️ Aucun contact valide détecté.")
        else:
            st.success(f"✅ {len(df)} contact(s) importé(s).")

            # Détection stricte de doublons exacts
            duplicate_phones = df['Telephone'][df['Telephone'].duplicated(keep=False) & (df['Telephone'] != "")]
            if not duplicate_phones.empty:
                st.warning(f"📞 {duplicate_phones.nunique()} numéro(s) de téléphone apparaissent plusieurs fois.")
                with st.expander("📋 Voir les numéros dupliqués"):
                    dup_phones_df = df[df['Telephone'].isin(duplicate_phones)]
                    st.dataframe(dup_phones_df, use_container_width=True)

            # Détection floue
            duplicates, duplicate_indices = detect_duplicates_fast(df)
            if duplicates:
                st.warning(f"⚠️ {len(duplicate_indices)} contact(s) potentiellement dupliqué(s) détecté(s).")
                with st.expander("🔍 Voir les doublons détectés"):
                    doublon_rows = []
                    for i, j, name_score, contact_score in duplicates:
                        row = {
                            "Index A": i,
                            "Nom A": df.at[i, "Full Name"],
                            "Téléphone A": df.at[i, "Telephone"],
                            "Email A": df.at[i, "Email"],
                            "Index B": j,
                            "Nom B": df.at[j, "Full Name"],
                            "Téléphone B": df.at[j, "Telephone"],
                            "Email B": df.at[j, "Email"],
                            "Simil. Nom (%)": name_score,
                            "Simil. Contact (%)": contact_score,
                        }
                        doublon_rows.append(row)
                    doublons_df = pd.DataFrame(doublon_rows)
                    st.dataframe(doublons_df, use_container_width=True)
            else:
                st.info("✅ Aucun doublon évident détecté.")

            # Édition
            st.subheader("📋 Modifier les contacts")
            edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)

            # Suppression
            if "deleted_rows" not in st.session_state:
                st.session_state.deleted_rows = []

            with st.form("edit_form"):
                index_to_delete = st.number_input(
                    "Index à supprimer (optionnel)", min_value=0,
                    max_value=len(edited_df)-1, step=1
                )
                delete = st.form_submit_button("🗑 Supprimer le contact")
                if delete:
                    st.session_state.deleted_rows.append(index_to_delete)
                    st.success(f"Contact à l'index {index_to_delete} supprimé")

            final_df = edited_df.drop(st.session_state.deleted_rows, errors='ignore').reset_index(drop=True)

            # Affichage final + export
            st.subheader("✅ Contacts finaux")
            st.dataframe(final_df, use_container_width=True)

            vcf_output = export_to_vcf(final_df)
            st.download_button(
                "💾 Télécharger le fichier VCF modifié",
                data=vcf_output,
                file_name="contacts_modifiés.vcf",
                mime="text/x-vcard"
            )

    except Exception as e:
        st.error("Une erreur est survenue pendant l'import ou le traitement du fichier.")
        st.exception(e)
