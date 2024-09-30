import os
import tiktoken
from dotenv import load_dotenv
from pypdf import PdfWriter, PdfReader
import google.generativeai as genai

# Configuration and constants
load_dotenv()
ROOT_DIRECTORY = os.path.dirname(os.path.realpath(__file__))
CACHE_FILE = 'api_cache.json'  # Currently unused, consider removing
MODEL_NAME = "gemini-1.5-flash-002"
MIN_CARDS = 75
MAX_CARDS = 200

# Configure Gemini
genai.configure(api_key=os.getenv('GOOGLE_API_KEY'))
model = genai.GenerativeModel(model_name=MODEL_NAME)

ROOT_DIRECTORY = os.path.dirname(os.path.realpath(__file__))
CACHE_FILE = 'api_cache.json'

class FlashcardGenerationError(Exception):
    pass

class UnauthorizedError(Exception):
    pass

def count_tokens(text):
    encoding = tiktoken.encoding_for_model('gpt2')
    return len(encoding.encode(text))
import re

def filter_pdf_pages(file_path, output_path):
    try:
        reader = PdfReader(file_path)
        writer = PdfWriter()
        total_pages = len(reader.pages)
        start_page = 2  # Simplified: Python indexing starts from 0
        end_page = total_pages

        name, ext = os.path.splitext(output_path)
        output_path = f"{name}_formatted_for_ai{ext}"

        for page_num in range(start_page, total_pages):
            page_text = reader.pages[page_num].extract_text()
            if re.search(r'Pokazn[ae]', page_text):
                end_page = page_num
                break

        for page_num in range(start_page, end_page):
            writer.add_page(reader.pages[page_num])

        with open(output_path, "wb") as f:
            writer.write(f)

        print(f"Filtered PDF saved to: {output_path}")
        return output_path

    except Exception as e:
        print(f"Error filtering PDF: {e}")
        return None



def create_flashcards_with_rate_limit(min_cards, max_cards, sample_pdf):

    max_retries = 3
    prompt = f"""Generiši Anki kartice na srpskom jeziku (latinica) iz priloženog PDF dokumenta, fokusirajući se na ključne koncepte, definicije, formule, dijagrame, tabele i važne detalje vezane za temu dokumenta.  Cilj je kreirati 10-15 kartica po poglavlju (osim ako nije drugačije navedeno), osiguravajući pokrivenost svih bitnih informacija. Ukupan broj kartica treba da bude između {min_cards} i {max_cards}, gde je {min_cards} minimum a {max_cards} maksimum. Minimum {min_cards} kartica je obavezan.  Ako dokument ne sadrži poglavlja, podeli ga na logičke celine i generiši 10-15 kartica po celini, ukupno kartica ne sme da predje {max_cards}, uvek se trudi da bude sto blize {max_cards}.

Pravila za kreiranje kartica:

1. Svaka kartica mora biti u jednom redu, formata "Pitanje?|Odgovor" ili "Objasni sledeći pojam '[pojam]':|Odgovor".
2. Pitanje mora završavati znakom pitanja.
3. Ne koristiti numeraciju, nabrajanje, uglaste zagrade, prefikse ili bilo kakvo formatiranje u pitanju ili odgovoru.
4. Odgovori moraju biti koncizni i jasni.
5. Koristiti isključivo srpski jezik (latinica, sr-Latn). Engleski jezik nije dozvoljen.
6. Za dijagrame, tabele i slike, kreirati kartice koje opisuju šta je prikazano i zašto je to važno.  Uključiti i relevantne podatke iz tabele ili dijagrama u odgovoru.
7.  Ignoriši delove teksta koji sadrže zadatke i rešenja, osim ako nije drugačije navedeno.
8. Kao odgovor vrati samo kartice bez dodatnih objasnjenja ili navodjenja iz kog su poglavlja. Format treba da bude takav da moze da se import u Anki direktno.
9. Potrudi se da kartice odgovaraju Anki filozofiji, dakle da budu koncizne i jasne.
10. NEMOJ DA PISES ==END OF DECK==
11. Dobro proceni najbitnije i kljucne koncepte, definicije, formule i slicno.
12. Ne ponavljaj pitanja.
Primeri:

Šta je fotosinteza?|Proces kojim biljke pretvaraju svetlosnu energiju u hemijsku.
Objasni sledeći pojam 'gravitacija':|Sila privlačenja između tela sa masom.


NAPOMENA: Strogo se pridržavati navedenih pravila i formata. Obavezno iskoristiti sav relevantan tekst iz PDF-a, osim ako nije drugačije navedeno.
       """

    for attempt in range(max_retries):
        try:
            response = model.generate_content([prompt, sample_pdf], generation_config=genai.GenerationConfig(
        max_output_tokens=8150,
        temperature=0.5,
    ), stream=True)
            response.resolve()
            flashcards = response.text
            return flashcards
        except Exception as e:
            error_message = str(e).lower()
            if "unauthorized" in error_message or "authentication" in error_message:
                raise UnauthorizedError("API key is invalid or unauthorized")
            raise FlashcardGenerationError(f"Failed to generate flashcards: {str(e)}")

def save_to_file(flashcards, output_path, encoding='utf-8'):
    try:
        with open(output_path, 'w', encoding=encoding, newline='') as f:
            for card in flashcards:
                f.write(card + '\n')
        print(f"Flashcards saved to {output_path}")
    except UnicodeEncodeError:
        print(f"Encoding error with {encoding}. Attempting to save with 'utf-8-sig' encoding...")
        try:
            with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
                for card in flashcards:
                    f.write(card + '\n')
            print(f"Flashcards saved to {output_path} with 'utf-8-sig' encoding")
        except Exception as e:
            print(f"Failed to save with 'utf-8-sig' encoding: {e}")
            raise
    except Exception as e:
        print(f"Error saving file: {e}")
        raise

def post_process_flashcards(flashcards):
    lines = flashcards.split('\n')
    processed_cards = []
    for line in lines:
        if '|' in line:
            question, answer = line.split('|', 1)
            # Remove leading numbers, dots, and whitespace
            question = re.sub(r'^\s*\d+\.\s*', '', question.strip())
            if question and not question.lower().startswith('pitanje?'):
                processed_cards.append(f"{question}|{answer}")
    return '\n'.join(processed_cards)

