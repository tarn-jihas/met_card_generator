import os
import threading
import time
import traceback
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from dotenv import load_dotenv
import google.generativeai as genai

from anki_flash import save_to_file, FlashcardGenerationError, UnauthorizedError, filter_pdf_pages, create_flashcards_with_rate_limit

load_dotenv()
API_KEY = os.getenv('GEMINI_API_KEY')
MODEL_NAME = "gemini-1.5-flash-latest"
MIN_CARDS = 75
MAX_CARDS = 200

if API_KEY:
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(model_name=MODEL_NAME)
else:
    print("GEMINI_API_KEY not found in .env file. Set API key using the GUI.")

class FlashcardGeneratorGUI:
    def __init__(self, master):
        self.master = master
        master.title("MET Flashcard Generator")
        master.geometry("400x450")
        master.configure(bg="#f0f0f0")

        self.setup_styles()
        self.create_variables()
        self.create_widgets()

        if not API_KEY:
            self.master.after(100, self.open_api_key_modal)

    def setup_styles(self):
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure('Blue.TButton', background="#4a7abc", foreground='white', padding=5)
        self.style.configure('Red.TButton', background="#bc4a4a", foreground='white', padding=5)
        self.style.configure("Blue.Horizontal.TProgressbar", troughcolor="#f0f0f0", background="#4a7abc")

    def create_variables(self):
        self.pdf_files = []
        self.pdf_paths = []
        self.output_path = tk.StringVar()
        self.output_name = tk.StringVar()
        self.stop_processing = False
        self.is_processing = False
        self.progress = tk.DoubleVar()
        self.api_key_modal_open = False

    def create_widgets(self):
        tk.Label(self.master, text="MET Flashcard Generator", font=("Helvetica", 16, "bold")).grid(row=0, column=0, columnspan=2, pady=(10, 5))

        ttk.Button(self.master, text="Select PDFs", command=self.browse_pdfs, style='Blue.TButton').grid(row=1, column=0, columnspan=2, sticky="ew", padx=20)
        self.pdf_listbox = tk.Listbox(self.master, width=40, height=5)
        self.pdf_listbox.grid(row=2, column=0, columnspan=2, sticky="ew", padx=20, pady=(0, 5))

        ttk.Button(self.master, text="Select Output File", command=self.browse_output, style='Blue.TButton').grid(row=3, column=0, sticky="w", padx=20)
        self.output_entry = tk.Entry(self.master, textvariable=self.output_path, width=25, state='readonly')
        self.output_entry.grid(row=3, column=1, sticky="e", padx=20)

        self.generate_button = ttk.Button(self.master, text="Generate Flashcards", command=self.generate_flashcards, style='Blue.TButton', state='disabled' if not API_KEY else 'normal')
        self.generate_button.grid(row=5, column=0, columnspan=2, pady=10, padx=20, sticky="ew")

        self.stop_button = ttk.Button(self.master, text="Stop Generation", command=self.stop_generation, style='Red.TButton', state='disabled')
        self.stop_button.grid(row=6, column=0, columnspan=2, pady=(0, 10), padx=20, sticky="ew")

        ttk.Button(self.master, text="Set API Key", command=self.open_api_key_modal, style='Blue.TButton').grid(row=7, column=0, columnspan=2, sticky="ew", padx=20)

        self.progressbar = ttk.Progressbar(self.master, variable=self.progress, maximum=100, length=360, style="Blue.Horizontal.TProgressbar")
        self.progressbar.grid(row=8, column=0, columnspan=2, pady=(0, 5), padx=20, sticky="ew")

        self.status_label = tk.Label(self.master, text="", wraplength=360)
        self.status_label.grid(row=9, column=0, columnspan=2, pady=(0, 10), padx=20, sticky="ew")

    def browse_pdfs(self):
        filenames = filedialog.askopenfilenames(filetypes=[("PDF files", "*.pdf")])
        self.pdf_files = []
        self.pdf_paths = list(filenames)
        for file in filenames:
            output_path = filter_pdf_pages(file, file)
            if output_path:
                uploaded_pdf = genai.upload_file(output_path)
                self.pdf_files.append(uploaded_pdf)

        self.pdf_listbox.delete(0, tk.END)
        for filename in self.pdf_paths:
            self.pdf_listbox.insert(tk.END, os.path.basename(filename))

        if self.pdf_paths:
            default_output = os.path.splitext(self.pdf_paths[0])[0] + "_flashcards.txt"
            self.output_path.set(default_output)
            self.output_name.set(os.path.basename(default_output))

    def browse_output(self):
        initial_dir = os.path.dirname(self.output_path.get()) if self.output_path.get() else os.path.dirname(self.pdf_paths[0]) if self.pdf_paths else os.path.expanduser("~")
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt")],
            initialdir=initial_dir,
            initialfile=self.output_name.get()
        )
        if filename:
            self.output_path.set(filename)
            self.output_name.set(os.path.basename(filename))

    def open_api_key_modal(self):
        if self.api_key_modal_open:
            return

        self.api_key_modal_open = True
        api_key_window = tk.Toplevel(self.master)
        api_key_window.title("Enter Google API Key")
        api_key_window.geometry("300x120")
        api_key_window.resizable(False, False)
        api_key_window.configure(bg="#f0f0f0")

        tk.Label(api_key_window, text="API Key:", font=("Helvetica", 10), bg="#f0f0f0").pack(pady=5)
        api_key_entry = tk.Entry(api_key_window, width=40, show="*", font=("Helvetica", 10))
        api_key_entry.pack(pady=5)

        def save_api_key():
            api_key = api_key_entry.get()
            if api_key:
                os.environ['GOOGLE_API_KEY'] = api_key
                with open('.env', 'w') as f:
                    f.write(f"GOOGLE_API_KEY={api_key}")
                messagebox.showinfo("Success", "API Key saved successfully!")
                print(f"Updated GOOGLE_API_KEY: {os.getenv('GOOGLE_API_KEY')}")
                self.generate_button.config(state='normal')
                api_key_window.destroy()
                self.api_key_modal_open = False
            else:
                messagebox.showerror("Error", "Please enter an API Key.")

        ttk.Button(api_key_window, text="Save", command=save_api_key, style='Blue.TButton').pack(pady=10)

        api_key_window.transient(self.master)
        api_key_window.grab_set()
        self.master.wait_window(api_key_window)

    def generate_flashcards(self):
        if not self.pdf_files or not self.output_path.get():
            messagebox.showerror("Error", "Please select at least one PDF and the output file path.")
            return

        if os.path.exists(self.output_path.get()):
            user_choice = messagebox.askyesno("File Exists", "The output file already exists. Do you want to overwrite it?")
            if not user_choice:
                return

        self.reset_gui_state()
        self.start_time = time.time()
        self.is_processing = True
        self.stop_processing = False
        self.generate_button.config(state='disabled')
        self.stop_button.config(state='normal')
        self.status_label.config(text="Processing...")
        self.processing_thread = threading.Thread(target=self.process_pdfs_thread, daemon=True)
        self.processing_thread.start()

    def stop_generation(self):
        if self.is_processing:
            self.stop_processing = True
            self.status_label.config(text="Stopping generation...")
            self.stop_button.config(state='disabled')

    def update_progress(self, value):
        self.progress.set(value)
        self.master.update_idletasks()

    def reset_gui_state(self):
        self.progress.set(0)
        self.status_label.config(text="", fg="black")
        self.progressbar.configure(style="Blue.Horizontal.TProgressbar")

    def process_pdfs_thread(self):
        try:
            all_flashcards = []

            for i, pdf in enumerate(self.pdf_files):
                if self.stop_processing:
                    break

                self.status_label.config(text=f"Generating cards for: {os.path.basename(self.pdf_paths[i])} ({i + 1}/{len(self.pdf_files)})")
                flashcards = create_flashcards_with_rate_limit(MIN_CARDS, MAX_CARDS, pdf)
                if flashcards:
                    all_flashcards.extend(flashcards.split('\n'))

                progress = ((i + 1) / len(self.pdf_files)) * 100
                self.progress.set(progress)
                self.master.update_idletasks()

            if self.stop_processing:
                self.status_label.config(text="Generation stopped by user.", fg="orange")
            else:
                total_cards = len(all_flashcards)
                expected_min = MIN_CARDS * len(self.pdf_files)
                expected_max = MAX_CARDS * len(self.pdf_files)
                if total_cards < expected_min:
                    messagebox.showwarning("Warning", f"Only {total_cards} cards were generated, which is less than the expected minimum of {expected_min}.")
                elif total_cards > expected_max:
                    messagebox.showwarning("Warning", f"{total_cards} cards were generated, which is more than the expected maximum of {expected_max}.")

                self.save_flashcards(all_flashcards)
                self.status_label.config(text=f"Processing completed. Generated {total_cards} cards.", fg="green")

        except UnauthorizedError as e:
            self.handle_unauthorized_error(str(e))
        except FlashcardGenerationError as e:
            self.handle_generation_error(str(e))
        except Exception as e:
            self.handle_unexpected_error(str(e))
        finally:
            self.is_processing = False
            self.stop_processing = False
            self.generate_button.config(state='normal')
            self.stop_button.config(state='disabled')

    def handle_unauthorized_error(self, error_message):
        self.progressbar.configure(style="Red.Horizontal.TProgressbar")
        self.status_label.config(text="API key unauthorized", fg="red")
        messagebox.showerror("Unauthorized", f"API key is unauthorized. Please check your API key.\n\nError: {error_message}")
        self.generate_button.config(state='disabled')
        self.master.after(100, self.open_api_key_modal)

    def handle_generation_error(self, error_message):
        self.progressbar.configure(style="Red.Horizontal.TProgressbar")
        self.status_label.config(text="Flashcard generation failed", fg="red")
        messagebox.showerror("Error", f"Flashcard generation failed:\n\n{error_message}")
        self.generate_button.config(state='normal')

    def handle_unexpected_error(self, error_message):
        self.progressbar.configure(style="Red.Horizontal.TProgressbar")
        self.status_label.config(text="An unexpected error occurred", fg="red")
        error_details = f"An unexpected error occurred:\n\n{error_message}\n\nStack Trace:\n{traceback.format_exc()}"
        messagebox.showerror("Unexpected Error", error_details)
        self.generate_button.config(state='normal')

    def save_flashcards(self, flashcards):
        if not self.output_path.get():
            messagebox.showerror("Error", "Please select an output file path.")
            return

        try:
            save_to_file(flashcards, self.output_path.get())
            messagebox.showinfo("Success", f"Flashcards saved to {self.output_path.get()}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save flashcards: {str(e)}")

if __name__ == "__main__":
    root = tk.Tk()
    app = FlashcardGeneratorGUI(root)
    root.mainloop()