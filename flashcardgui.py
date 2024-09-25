import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import os
import threading
import traceback
import time
from dotenv import load_dotenv
from tinydb import TinyDB

from anki_flash import save_to_file, clear_cache, process_multiple_pdfs, FlashcardGenerationError, UnauthorizedError

load_dotenv()


class FlashcardGeneratorGUI:
    def __init__(self, master):
        self.master = master
        master.title("MET Flashcard Generator")
        master.geometry("400x520")
        master.resizable(False, False)


        self.bg_color = "#f0f0f0"
        self.button_color = "#4a7abc"
        self.text_color = "#333333"
        self.title_font = ("Helvetica", 16, "bold")
        self.label_font = ("Helvetica", 10)
        self.button_font = ("Helvetica", 10, "bold")

        master.configure(bg=self.bg_color)

        self.pdf_paths = []
        self.output_path = tk.StringVar()
        self.output_name = tk.StringVar()
        self.stop_processing = False

        self.start_time = None
        self.is_processing = False
        self.total_chunks = 0
        self.processed_chunks = 0
        self.last_chunk_time = None
        self.current_pdf = None
        self.current_pdf_index = 0

        self.create_widgets()
        self.style_config()

        self.current_pdf_chunks = 0
        self.current_pdf_processed_chunks = 0
        self.chunk_processing_time = 0

        self.check_existing_api_key()
        self.progress = tk.DoubleVar()
        self.chunking_complete = False
        self.api_key_modal_open = False
        self.api_key_entry = None


    def open_api_key_modal(self):
        if self.api_key_modal_open:
            return
    def create_widgets (self):
        # Title
        tk.Label(self.master, text="MET Flashcard Generator", font=self.title_font, bg=self.bg_color,
                 fg=self.text_color).pack(pady=10)

        # Frame for file selection
        file_frame = tk.Frame(self.master, bg=self.bg_color)
        file_frame.pack(fill='x', padx=20, pady=5)

        # PDF selection
        ttk.Button(file_frame, text="Select PDFs", command=self.browse_pdfs, style='Blue.TButton').pack(fill='x',
                                                                                                        pady=5)

        # Listbox for selected PDFs
        self.pdf_listbox = tk.Listbox(file_frame, width=50, height=5, font=self.label_font, relief='flat', bd=1)
        self.pdf_listbox.pack(fill='x', pady=5)

        # Output file selection
        output_frame = tk.Frame(file_frame, bg=self.bg_color)
        output_frame.pack(fill='x', pady=5)
        ttk.Button(output_frame, text="Select Output File", command=self.browse_output, style='Blue.TButton').pack(
            side='left')
        tk.Entry(output_frame, textvariable=self.output_name, width=30, font=self.label_font, state='readonly',
                 relief='flat').pack(side='left', padx=5)

        # Clear cache option
        self.clear_cache_var = tk.BooleanVar()
        tk.Checkbutton(self.master, text="Clear cache before processing", variable=self.clear_cache_var,
                       font=self.label_font, bg=self.bg_color, fg=self.text_color).pack(pady=5)

        # Generate button (initially disabled)
        self.generate_button = ttk.Button(self.master, text="Generate Flashcards", command=self.generate_flashcards,
                                          style='Blue.TButton', state='disabled')
        self.generate_button.pack(pady=10)

        # Stop button (initially disabled)
        self.stop_button = ttk.Button(self.master, text="Stop Generation", command=self.stop_generation,
                                      style='Red.TButton', state='disabled')
        self.stop_button.pack(pady=5)

        # Set API Key button
        ttk.Button(self.master, text="Set API Key", command=self.open_api_key_modal, style='Blue.TButton').pack(pady=5)

        # Progress bar
        self.progress = tk.DoubleVar()
        self.progressbar = ttk.Progressbar(self.master, variable=self.progress, maximum=100, length=360,
                                           style="Blue.Horizontal.TProgressbar")
        self.progressbar.pack(pady=10)

        # Status label
        self.status_label = tk.Label(self.master, text="", font=self.label_font, bg=self.bg_color, fg=self.text_color,
                                     wraplength=360)
        self.status_label.pack(pady=5)

    def style_config(self):
        style = ttk.Style()
        style.theme_use('clam')

        # Configure blue button style
        style.configure('Blue.TButton',
                        background=self.button_color,
                        foreground='white',
                        font=self.button_font,
                        padding=5,
                        relief='flat')
        style.map('Blue.TButton',
                  background=[('active', '#3a5a8c'), ('pressed', '#2a4a7c')],
                  relief=[('pressed', 'sunken')])

        # Configure red button style
        style.configure('Red.TButton',
                        background='#bc4a4a',
                        foreground='white',
                        font=self.button_font,
                        padding=5,
                        relief='flat')
        style.map('Red.TButton',
                  background=[('active', '#8c3a3a'), ('pressed', '#7c2a2a')],
                  relief=[('pressed', 'sunken')])

        # Configure blue progress bar
        style.configure("Blue.Horizontal.TProgressbar",
                        troughcolor=self.bg_color,
                        background=self.button_color,
                        darkcolor=self.button_color,
                        lightcolor=self.button_color)

    def browse_pdfs(self):
        filenames = filedialog.askopenfilenames(filetypes=[("PDF files", "*.pdf")])
        if filenames:
            self.pdf_paths = list(filenames)
            self.pdf_listbox.delete(0, tk.END)
            for filename in self.pdf_paths:
                self.pdf_listbox.insert(tk.END, os.path.basename(filename))

            # Set default output path
            default_output = os.path.splitext(self.pdf_paths[0])[0] + "_flashcards.txt"
            self.output_path.set(default_output)
            self.output_name.set(os.path.basename(default_output))

    def browse_output(self):
        initial_dir = os.path.dirname(self.output_path.get()) if self.output_path.get() else os.path.dirname(
            self.pdf_paths[0]) if self.pdf_paths else os.path.expanduser("~")
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
        api_key_window.title("Enter Mistral API Key")
        api_key_window.geometry("300x120")
        api_key_window.resizable(False, False)
        api_key_window.configure(bg=self.bg_color)

        tk.Label(api_key_window, text="API Key:", font=self.label_font, bg=self.bg_color).pack(pady=5)
        api_key_entry = tk.Entry(api_key_window, width=40, show="*", font=self.label_font)
        api_key_entry.pack(pady=5)

        def save_api_key():
            api_key = api_key_entry.get()
            if api_key:
                os.environ['MISTRAL_API_KEY'] = api_key
                # Update the .env file
                with open('.env', 'w') as f:
                    f.write(f"MISTRAL_API_KEY={api_key}")
                messagebox.showinfo("Success", "API Key saved successfully!")
                print(f"Updated MISTRAL_API_KEY: {os.getenv('MISTRAL_API_KEY')}")
                self.generate_button.config(state='normal')  # Enable the generate button
                api_key_window.destroy()
            else:
                messagebox.showerror("Error", "Please enter an API Key.")

        ttk.Button(api_key_window, text="Save", command=save_api_key, style='Blue.TButton').pack(pady=10)

        # Make the API key window modal
        api_key_window.transient(self.master)
        api_key_window.grab_set()
        self.master.wait_window(api_key_window)

    def generate_flashcards(self):
        if not self.pdf_paths or not self.output_path.get():
            messagebox.showerror("Error", "Please select at least one PDF and the output file path.")
            return

        # Check if file exists and ask user what to do before processing
        if os.path.exists(self.output_path.get()):
            user_choice = messagebox.askyesno("File Exists",
                                              "The output file already exists. Do you want to overwrite it?")
            if not user_choice:
                return  # User chose not to overwrite, so we stop here

        self.reset_gui_state()

        if self.clear_cache_var.get():
            clear_cache()

        # Reset processing variables
        self.start_time = time.time()
        self.is_processing = True
        self.stop_processing = False

        # Disable generate button and enable stop button
        self.generate_button.config(state='disabled')
        self.stop_button.config(state='normal')

        # Start processing in a separate thread to keep GUI responsive
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
        """Reset the GUI state before starting a new process."""
        self.progress.set(0)
        self.status_label.config(text="", fg=self.text_color)
        self.progressbar.configure(style="Blue.Horizontal.TProgressbar")

    def process_pdfs_thread(self):
        try:
            self.start_time = time.time()
            self.chunking_complete = False

            def progress_callback(pdf_path, current_index, total, stage):
                if self.stop_processing:
                    return False  # Signal to stop processing
                if stage == 'chunking':
                    pdf_name = os.path.basename(pdf_path)
                    self.status_label.config(text=f"Chunking: {pdf_name} ({current_index + 1}/{total})")
                    progress = ((current_index + 1) / total) * 100
                elif stage == 'chunking_complete':
                    self.chunking_complete = True
                    self.progress.set(0)  # Reset progress bar to 0
                    self.status_label.config(text="Chunking complete. Starting card generation...")
                    self.master.update_idletasks()
                    return
                else:  # 'generating'
                    self.status_label.config(text=f"Generating cards: Chunk {current_index + 1}/{total}")
                    progress = ((current_index + 1) / total) * 100

                self.progress.set(progress)
                self.master.update_idletasks()

            all_flashcards = process_multiple_pdfs(self.pdf_paths, progress_callback)
            if self.stop_processing:
                self.status_label.config(text="Generation stopped by user.", fg="orange")
            else:
                total_cards = len(all_flashcards.split('\n'))
                expected_min = 100 * len(self.pdf_paths)
                expected_max = 200 * len(self.pdf_paths)
                if total_cards < expected_min:
                    messagebox.showwarning("Warning",
                                           f"Only {total_cards} cards were generated, which is less than the expected minimum of {expected_min}.")
                elif total_cards > expected_max:
                    messagebox.showwarning("Warning",
                                           f"{total_cards} cards were generated, which is more than the expected maximum of {expected_max}.")

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
        messagebox.showerror("Unauthorized",
                             f"API key is unauthorized. Please check your API key.\n\nError: {error_message}")
        self.generate_button.config(state='disabled')
        self.open_api_key_modal()  # Open the API key modal to allow the user to enter a new key
        self.master.after(100, self.open_api_key_modal)


    def handle_generation_error(self, error_message):
        self.progressbar.configure(style="Red.Horizontal.TProgressbar")
        self.status_label.config(text="Flashcard generation failed", fg="red")
        messagebox.showerror("Error", f"Flashcard generation failed:\n\n{error_message}")
        self.generate_button.config(state='normal')  # Re-enable the generate button to allow retry

    def handle_unexpected_error(self, error_message):
        self.progressbar.configure(style="Red.Horizontal.TProgressbar")
        self.status_label.config(text="An unexpected error occurred", fg="red")
        error_details = f"An unexpected error occurred:\n\n{error_message}\n\nStack Trace:\n{traceback.format_exc()}"
        messagebox.showerror("Unexpected Error", error_details)
        self.generate_button.config(state='normal')  # Re-enable the generate button to allow retry
    def save_flashcards(self, flashcards):
        if not self.output_path.get():
            messagebox.showerror("Error", "Please select an output file path.")
            return

        try:
            # Split the flashcards string into a list of individual flashcards
            flashcard_list = flashcards.split('\n')
            save_to_file(flashcard_list, self.output_path.get())
            messagebox.showinfo("Success", f"Flashcards saved to {self.output_path.get()}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save flashcards: {str(e)}")
    def save_api_key_to_db(self, api_key):
        db = TinyDB('api_keys.json')
        db.insert({'api_key': api_key}) # TODO NAMESTI TINY DB MRZI ME AAAAAAAAAAAAAAAAAAAAAAA
    def check_existing_api_key(self):
        api_key = os.getenv('MISTRAL_API_KEY')
        if api_key:
            self.generate_button.config(state='normal')
        else:
            self.generate_button.config(state='disabled')
            if not self.api_key_modal_open:
                self.master.after(100, self.open_api_key_modal)




if __name__ == "__main__":
    root = tk.Tk()
    app = FlashcardGeneratorGUI(root)
    root.mainloop()