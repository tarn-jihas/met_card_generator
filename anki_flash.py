import os
import json
import time
import re
from mistralai import Mistral
import tiktoken
import pdfplumber
from dotenv import load_dotenv

ROOT_DIRECTORY = os.path.dirname(os.path.realpath(__file__))
CACHE_FILE = 'api_cache.json'

load_dotenv()
# Initialize Mistral client
client = Mistral(api_key=os.getenv('MISTRAL_API_KEY'))

model = "mistral-small-latest"

class FlashcardGenerationError(Exception):
    pass

class UnauthorizedError(Exception):
    pass

def count_tokens(text):
    encoding = tiktoken.encoding_for_model('gpt2')
    return len(encoding.encode(text))

def read_pdf(file_path):
    with pdfplumber.open(file_path) as pdf:
        text = ""
        for page_num, page in enumerate(pdf.pages[2:], start=2):  # Počinjemo od treće strane (indeks 2)
            page_text = page.extract_text()
            if page_text:
                # Provera da li stranica sadrži "Pokazne vežbe" ili "Pokazne Vežbe"
                if re.search(r'Pokazne\s*[Vv]ežbe', page_text):
                    # Ako sadrži, prekidamo čitanje
                    break
                elif   re.search(r'Pokazna\s*[Vv]ežba', page_text):
                    break
                else:
                    text += page_text + "\n"
        return text.strip()


def chunk_text(text, target_size, tolerance=0.1):
    min_size = int(target_size * (1 - tolerance))
    max_size = int(target_size * (1 + tolerance))
    result = []
    current_index = 0

    def find_break(start, end):
        # Define break characters and their priorities
        break_chars = [('\n\n', 4), ('\n', 3), ('.', 2), ('!', 2), ('?', 2), (',', 1), (' ', 0)]

        for char, priority in break_chars:
            for i in range(end, start - 1, -1):
                if text[i:i + len(char)] == char:
                    # For sentence-ending punctuation, ensure it's followed by a space or end of text
                    if priority == 2 and i + 1 < len(text) and not text[i + 1].isspace():
                        continue
                    return i + len(char), priority

        # If all else fails, just break at the maximum point
        return end, -1

    while current_index < len(text):
        if current_index + min_size >= len(text):
            # If the remaining text is shorter than min_size, just add it as the last chunk
            chunk = text[current_index:].strip()
            if chunk:
                result.append(chunk)
            break

        end_index = min(current_index + max_size, len(text))

        break_point, priority = find_break(current_index + min_size, end_index)

        # If we're breaking mid-word, try to find a better break point
        if priority < 0 and break_point < len(text) and not text[break_point].isspace():
            better_break, _ = find_break(current_index, break_point)
            if better_break > current_index:
                break_point = better_break

        chunk = text[current_index:break_point].strip()
        if chunk:  # Only add non-empty chunks
            result.append(chunk)

        current_index = break_point

    return result


def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_cache(cache):
    with open(CACHE_FILE, 'w') as f:
        json.dump(cache, f)


def create_flashcards_with_rate_limit(text, cache, min_cards, max_cards):

    if cache and text in cache:
        return cache[text]

    max_retries = 3

    for attempt in range(max_retries):
        try:
            chat_response = client.chat.complete(
                model=model,
                messages=[
                    {"role": "system",
                     "content": "Ti si asistent koji generiše flash kartice ISKLJUČIVO na srpskom jeziku (latinica). Ne smeš koristiti engleski jezik ni u jednom trenutku."},
                    {"role": "user", "content": f"""Kreiraj Anki kartice na srpskom jeziku (latinica) iz ovog teksta. Fokusiraj se na ključne koncepte, definicije i važne detalje.

            Pravila za kreiranje kartica:
            1. Ne koristi numeraciju ili nabrajanje niti bilo kakvo formatiranje.
            2. Ne koristi nikakve prefikse.
            3. Pitanje treba da se završi znakom pitanja.
            4. Ne koristi uglaste zagrade u odgovoru.
            5. Svaka kartica treba da bude u jednom redu, sa pitanjem i odgovorom razdvojenim znakom '|'.
            6. Kreiraj između {min_cards} i {max_cards} flash kartica, baziranih na tekstu koji ti je dat. VAŽNO: Obavezno generiši NAJMANJE {min_cards} kartica za ovaj deo teksta.
            7. Svaka kartica MORA biti na srpskom jeziku, koristeći latinicu (sr-Latn). NIKAKO ne koristi engleski jezik.
            8. Iskoristi sav dostupni tekst i pokrij sve važne informacije iz njega.

            Format za svaku karticu:
            Pitanje?|Odgovor
            ILI
            Objasni sledeći pojam 'ovde ubaci pojam':|Odgovor

            Primer dobre kartice: Šta su osnovna sekvencijalna kola?|Osnovna sekvencijalna kola su SR-latch kolo i D-flip-flop.
            Još jedan primer dobre kartice: Objasni kako se formira memorija sa većim m.|Memorija sa većim m se formira paralelnim vezivanjem nekoliko memorijskih čipova.

            Tekst: {text}"""}
                ]
            )

            flashcards = chat_response.choices[0].message.content
            cache[text] = flashcards
            save_cache(cache)
            return flashcards
        except Exception as e:
            error_message = str(e).lower()
            if "unauthorized" in error_message or "authentication" in error_message:
                raise UnauthorizedError("API key is invalid or unauthorized")
            print(f"Error on attempt {attempt + 1}: {e}")
            if attempt == max_retries - 1:
                raise FlashcardGenerationError(
                    f"Failed to generate flashcards after {max_retries} attempts. Last error: {str(e)}")
            time.sleep(2 ** attempt)  # Exponential backoff


def process_multiple_pdfs(pdf_paths, progress_callback=None):
    all_flashcards = []
    total_pdfs = len(pdf_paths)
    all_chunks = []
    cache = load_cache()
    # Chunking stage
    for pdf_index, pdf_path in enumerate(pdf_paths):
        if progress_callback:
            progress_callback(pdf_path, pdf_index, total_pdfs, 'chunking')

        text = read_pdf(pdf_path)
        chunks = chunk_text(text, target_size=4000)
        all_chunks.append((pdf_path, chunks))

    # Signal end of chunking stage
    if progress_callback:
        progress_callback(None, total_pdfs, total_pdfs, 'chunking_complete')

    # Generating stage
    total_chunks = sum(len(chunks) for _, chunks in all_chunks)
    processed_chunks = 0

    for pdf_path, chunks in all_chunks:
        pdf_min_cards = 100
        pdf_max_cards = 200
        chunk_count = len(chunks)

        for chunk_index, chunk in enumerate(chunks):
            if progress_callback:
                progress_callback(pdf_path, processed_chunks, total_chunks, 'generating')

            # Calculate min and max cards for this chunk
            chunk_min_cards = max(1, pdf_min_cards // chunk_count)
            chunk_max_cards = max(chunk_min_cards, pdf_max_cards // chunk_count)

            # Adjust for last chunk to ensure we meet the minimum
            if chunk_index == chunk_count - 1:
                chunk_min_cards = max(chunk_min_cards, pdf_min_cards - (chunk_count - 1) * chunk_min_cards)
                chunk_max_cards = max(chunk_max_cards, pdf_max_cards - (chunk_count - 1) * chunk_max_cards)

            flashcards = create_flashcards_with_rate_limit(chunk, cache, chunk_min_cards, chunk_max_cards)
            if flashcards:
                all_flashcards.extend(flashcards.split('\n'))

            processed_chunks += 1

    return post_process_flashcards('\n'.join(all_flashcards))


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

def clear_cache():
    global cache
    cache = {}
    save_cache(cache)
    print("Cache cleared.")

#
# if __name__ == "__main__":
#     pdf_path = f'{ROOT_DIRECTORY}/SOURCE_DOCUMENTS/CS120-L04.pdf'
#     # Add an option to clear the cache before processing
#     clear_cache_input = input("Da li želite da obrišete keš pre obrade? (da/ne): ").lower()
#     if clear_cache_input == 'da':
#         clear_cache()
#
#     flashcards = process_pdf(pdf_path)
#     save_to_file(flashcards)