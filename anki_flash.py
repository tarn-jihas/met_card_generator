import os
import json
import time
import re as regex

from mistralai import Mistral
import tiktoken
from tqdm import tqdm
import pdfplumber

ROOT_DIRECTORY = os.path.dirname(os.path.realpath(__file__))
CACHE_FILE = 'api_cache.json'


# Initialize Mistral client
client = Mistral(api_key='wBaJcoccc4z85HMNz0RWVhP3fc2wDYQO')
model = "mistral-small-latest"


def count_tokens(text):
    encoding = tiktoken.encoding_for_model('gpt2')
    return len(encoding.encode(text))

def read_pdf(file_path):
    with pdfplumber.open(file_path) as pdf:
        return "\n".join(page.extract_text() for page in pdf.pages if page.extract_text())



def chunk_text(text, target_size, tolerance=0.1):
    min_size = int(target_size * (1 - tolerance))
    max_size = int(target_size * (1 + tolerance))
    result = []
    current_index = 0

    while current_index < len(text):
        end_index = min(current_index + target_size, len(text))

        # Adjust end_index to not split in the middle of a word
        while end_index < len(text) and text[end_index] != ' ' and text[end_index - 1] != ' ':
            end_index += 1

        # Try to find the closest paragraph break within the tolerance range
        paragraph_end = end_index
        while paragraph_end < len(text) and paragraph_end < current_index + max_size and text[paragraph_end] != '\n':
            paragraph_end += 1
        while paragraph_end > current_index and paragraph_end > current_index + min_size and text[
            paragraph_end] != '\n':
            paragraph_end -= 1

        # If we found a paragraph end within the range, use it; otherwise, stick with the closest word end
        if current_index + min_size < paragraph_end < current_index + max_size:
            end_index = paragraph_end

        result.append(text[current_index:end_index].strip())
        current_index = end_index + 1  # Skip the paragraph break or space

    return result

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r') as f:
            return json.load(f)
    return {}


def save_cache(cache):
    with open(CACHE_FILE, 'w') as f:
        json.dump(cache, f)


def create_flashcards_with_rate_limit(text, cache):
    if text in cache:
        return cache[text]

    max_retries = 3

    for attempt in range(max_retries):
        try:
            chat_response = client.chat.complete(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that creates Anki flashcards in Serbian."},
                    {"role": "user", "content": f"""Kreiraj Anki kartice na srpskom jeziku iz ovog teksta. Fokusiraj se na ključne koncepte, definicije i važne detalje.
    
    Pravila za kreiranje kartica:
    1. Ne koristi numeraciju ili nabrajanje niti bilo kakvo formatiranje.
    2. Ne dodaj prefikse 'Pitanje:' ili 'Odgovor:'.
    3. Pitanje treba da se završi znakom pitanja.
    4. Ne koristi uglaste zagrade u odgovoru.
    5. Svaka kartica treba da bude u jednom redu, sa pitanjem i odgovorom razdvojenim znakom '|'.
    5. Zadatak ti je da kreiras koliko je god moguce kartica (75-200), baziranih na tekstu koji ti je dat.
    
    Format za svaku karticu:
    Pitanje?|Odgovor
    ILI
    Objasni sledeci pojam 'ovde ubaci pojam':|Odgovor
    
    Primer dobre kartice: Šta su osnovna sekvencijalna kola?|Osnovna sekvencijalna kola su SR-latch kolo i D-flip-flop.

    
    Tekst: {text}"""}
                ]
            )

            flashcards = chat_response.choices[0].message.content
            cache[text] = flashcards
            save_cache(cache)
            return flashcards
        except Exception as e:
            print(f"Error on attempt {attempt + 1}: {e}")
            if attempt == max_retries - 1:
                print("Max retries reached. Skipping this chunk.")
                return ""
            time.sleep(2 ** attempt)  # Exponential backoff


def process_pdf(pdf_path):
    text = read_pdf(pdf_path)
    chunks = chunk_text(text, target_size=3000)
    cache = load_cache()

    all_flashcards = []
    total_tokens = 0

    # Initialize tqdm with total number of chunks
    pbar = tqdm(total=len(chunks), desc="Processing chunks")

    for i, chunk in enumerate(chunks):
        pbar.set_description(f"Processing chunk {i + 1}/{len(chunks)}")
        flashcards = create_flashcards_with_rate_limit(chunk, cache)
        if flashcards:
            all_flashcards.append(flashcards)
            total_tokens += count_tokens(chunk)

        # Update progress bar
        pbar.update(1)

        # Optional: Add a small delay to make the progress visible
        time.sleep(0.1)

    # Close the progress bar
    pbar.close()

    all_flashcards = post_process_flashcards('\n'.join(all_flashcards))
    print(f"Total tokens used: {total_tokens}")

    return all_flashcards


def save_to_file(text, filename="kartice.txt"):
    with open(filename, "w", encoding='utf-8') as f:
        f.write(text)
    print(f"Kartice sačuvane u {filename}")

def post_process_flashcards(flashcards):
    lines = flashcards.split('\n')
    processed_cards = []
    for line in lines:
        if '|' in line:
            question, answer = line.split('|', 1)
            # Remove leading numbers, dots, and whitespace
            question = regex.sub(r'^\s*\d+\.\s*', '', question.strip())
            if question and not question.lower().startswith('pitanje?'):
                processed_cards.append(f"{question}|{answer}")
    return '\n'.join(processed_cards)

def clear_cache():
    global cache
    cache = {}
    save_cache(cache)
    print("Cache cleared.")


if __name__ == "__main__":
    pdf_path = f'{ROOT_DIRECTORY}/SOURCE_DOCUMENTS/CS120-L04.pdf'
    # Add an option to clear the cache before processing
    clear_cache_input = input("Da li želite da obrišete keš pre obrade? (da/ne): ").lower()
    if clear_cache_input == 'da':
        clear_cache()

    flashcards = process_pdf(pdf_path)
    save_to_file(flashcards)