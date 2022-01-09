"""
Graphisches Programm zum sortieren von Bildern in verschiedene Ordner.
"""


from typing import List, Dict, Callable, Tuple, Optional

import imghdr

import tkinter as tk
from tkinter import ttk, N, E, S, W
import tkinter.filedialog as tkfd
import tkinter.messagebox as tkmb

import pathlib
import shutil

import copy

from dataclasses import dataclass

import argparse
import sys

import PIL.Image
import PIL.ImageTk


# Note tkinter-lifetime
# Assignments such as
#   image = ttk.Label(self, image=photo)
#   image.image = photo
# seem strange and redundant (and raise a mypy warning because image has not
# member image) but they are necessary!
# This makes sure, that the photo is not garbage collected -- see
# https://web.archive.org/web/20201111190625/http://effbot.org/pyfaq/why-do-my-tkinter-images-not-appear.htm


def get_images_in(directory: pathlib.Path) -> List[pathlib.Path]:
    entities = directory.glob("*")
    files = [x for x in entities if x.is_file()]
    images = [x for x in files if imghdr.what(x) is not None]
    sorted_images = sorted(images)
    return sorted_images


def get_expected_file_in_directory(file: pathlib.Path, directory: pathlib.Path) -> pathlib.Path:
    """
    Return the expected file in the directory -- the file may exist or not.
    """
    expected_file = directory / file.name
    return expected_file


def is_file_in_directory(file: pathlib.Path, directory: pathlib.Path) -> bool:
    """
    Check, whether a file with the same filename exists in the given directory.
    """
    if not directory.is_dir():
        raise ValueError(f"{directory} is not a directory.")
    expected_file = get_expected_file_in_directory(file, directory)
    return expected_file.exists() and expected_file.is_file()


def copy_file_to_directory(file: pathlib.Path, directory: pathlib.Path) -> None:
    """
    Copy given file to the given directory.
    """
    if is_file_in_directory(file, directory):
        print(f"File {file} already in {directory}")
        return
    print(f"Copy {file} to {directory}", end="... ")
    shutil.copy(file, directory)
    print("done")


def delete_file_in_directory(file: pathlib.Path, directory: pathlib.Path) -> None:
    """
    Delete the given file (name) in the given given directory.
    """
    expected_file = get_expected_file_in_directory(file, directory)
    if not expected_file.exists():
        print(f"File {file} not in {directory}")
        return
    if not expected_file.is_file():
        raise ValueError(f"File {file} in {directory} (i.e. {expected_file} is not a file.")
    print(f"Delete {file} in {directory}, i.e. {expected_file}", end="... ")
    expected_file.unlink()
    print("done")


class FileAction:
    """
    Callable that contains all the information to copy/delete/... a file to a destination.

    Note: The ``action`` to perform is not copied.

    Use this in a callback to make sure that the file/destination is "immutable"
    -- i.e. that they are not changed if the variables used to denote
    file/destination get a new value.
    """

    def __init__(
        self,
        file: pathlib.Path,
        directory: pathlib.Path,
        action: Callable[[pathlib.Path, pathlib.Path], None],
    ) -> None:
        self.source = copy.deepcopy(file)
        self.destination = copy.deepcopy(directory)
        self.action = action
        self.callbacks: List[Callable[[], None]] = []

    def __call__(self):
        self.action(self.source, self.destination)
        for callback in self.callbacks:
            callback()


def set_button_active(button: ttk.Button, should_be_active: bool) -> None:
    command = "!disabled" if should_be_active else "disabled"
    button.state([command])


@dataclass
class FileCopyUI:
    """
    The UI elements and metadata responsible to copy/delete/... files.
    """

    file: pathlib.Path
    destination_directory: pathlib.Path
    current_state: ttk.Label
    copy_button: ttk.Button
    delete_button: ttk.Button

    def update(self) -> None:
        """
        Update state of UI according to files found on disk.
        """
        is_copied = is_file_in_directory(self.file, self.destination_directory)
        text_prefix = "schon" if is_copied else "noch nicht"

        self.current_state["text"] = f"{text_prefix} in {self.destination_directory.name}"
        self.current_state["background"] = "green" if is_copied else "blue"
        self.current_state["foreground"] = "black" if is_copied else "white"

        set_button_active(self.copy_button, not is_copied)
        set_button_active(self.delete_button, is_copied)


class SelectableImage(ttk.Frame):
    """
    UI elements to display a single image and the information in what
    destination directories it is available.
    """

    def draw(self):
        """
        Update the image to display.
        Currently the logic for file actions will fail if we change the name as
        the FileActions still have the old name set.
        """
        # image
        content = PIL.Image.open(self.file)
        content.thumbnail(self.size, PIL.Image.ANTIALIAS)
        photo = PIL.ImageTk.PhotoImage(content)
        self.image["image"] = photo
        self.image.image = photo  # type: ignore  See tkinter-lifetime above
        # label
        self.label["text"] = self.file.name
        # controls
        for ui in self.file_uis.values():
            ui.update()

    def __init__(
        self,
        parent: ttk.Frame,
        file: pathlib.Path,
        destination_directories: List[pathlib.Path],
        size: Tuple[int, int] = (300, 300),
    ):
        super().__init__(parent)

        self.file = file
        self.size = size

        self.image = ttk.Label(self)
        self.image.grid(column=0, row=0)

        self.label = ttk.Label(self, text=file.name)
        self.label.grid(column=0, row=1)

        destinations = ttk.Frame(self)

        self.file_uis: Dict[str, FileCopyUI] = {}

        for index, possible_destination in enumerate(destination_directories):
            is_copied = is_file_in_directory(file, possible_destination)
            text_prefix = "schon" if is_copied else "noch nicht"
            state = ttk.Label(
                destinations,
                text=f"{text_prefix} in {possible_destination.name}",
                background="green" if is_copied else "blue",
            )
            state.grid(row=0, column=index)
            copyer = FileAction(file, possible_destination, copy_file_to_directory)
            copy_button = ttk.Button(
                destinations,
                text=f"Kopiere nach {possible_destination.name}",
                command=copyer,
            )
            copy_button.grid(row=1, column=index)
            deleter = FileAction(file, possible_destination, delete_file_in_directory)
            delete_button = ttk.Button(
                destinations,
                text=f"Loesche in {possible_destination.name}",
                command=deleter,
            )
            delete_button.grid(row=2, column=index)

            ui = FileCopyUI(
                file=file,
                destination_directory=possible_destination,
                current_state=state,
                copy_button=copy_button,
                delete_button=delete_button,
            )

            for action in [copyer, deleter]:
                action.callbacks.append(ui.update)

            self.file_uis[possible_destination] = ui

        destinations.grid(column=0, row=2)

        self.draw()


class CurrentImagesProvider:
    """
    The logic to display one or a list of current images.
    """

    def __init__(self, source_directory: pathlib.Path) -> None:
        self.images = get_images_in(source_directory)
        self.current = 0

    def skim(self, number_of_images: int):
        """
        Go ``number_of_images`` to the next (positive) or previous (negative)
        image.
        """
        self.current = max(0, min(self.current + number_of_images, len(self.images) - 1))

    def get(self, number_of_images: int) -> List[pathlib.Path]:
        """
        Return paths to ``number_of_images`` images (or less, if only less are available).
        """
        # corner case: too few images
        if len(self.images) < number_of_images:
            print(f"Only {len(self.images)} images available, but {number_of_images} requested.")
            number_of_images = len(self.images)
        # corner case: current image too close to the end of images
        index = self.current
        if index + number_of_images > len(self.images):
            index = len(self.images) - number_of_images
            print(f"Already at image num {self.current} of {len(self.images)} -- showing from image num {index}.")
        images = self.images[index : index + number_of_images]
        return images

    def progress(self) -> float:
        """
        Return progress in percent.
        """
        return (100 * (self.current + 1)) / len(self.images)


class PhotoSelectionGUI:
    """
    UI to display controls and images to copy.
    """

    def __init__(
        self,
        root: tk.Tk,
        source_directory: pathlib.Path,
        destination_directories: List[pathlib.Path],
    ) -> None:

        for folder in [source_directory] + destination_directories:
            if not folder.exists() or not folder.is_dir():
                raise ValueError(f"{folder} is not a directory.")

        self.images_provider = CurrentImagesProvider(source_directory)

        root.title("Photobuchauswahltool")

        mainframe = ttk.Frame(root, padding="3 3 12 12")
        mainframe.grid(column=0, row=0, sticky=(N, W, E, S))
        # fill extra space if window is resized
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        # BEGIN frame with actions/overview/... next to the actual images
        actions_frame = ttk.Frame(mainframe)
        ttk.Label(actions_frame, text="Bild:").grid(row=0, column=0)
        back_button = ttk.Button(actions_frame, text="<-", command=self.previous_image)
        back_button.grid(row=1, column=0)
        forward_button = ttk.Button(actions_frame, text="->", command=self.next_image)
        forward_button.grid(row=2, column=0)
        ttk.Label(actions_frame, text="Anzahl Bilder:").grid(row=10, column=0)
        num_images = tk.IntVar(root, value=1)
        num_images_spinbox = ttk.Spinbox(
            actions_frame,
            from_=1,
            increment=1,
            to=11,
            textvariable=num_images,
            width=5,
        )
        num_images_spinbox.grid(row=11, column=0)
        num_images_spinbox.value = num_images  # type: ignore  See tkinter-lifetime above
        ttk.Label(actions_frame, text="Groesse:").grid(row=20, column=0)
        size_images = tk.IntVar(root, value=500)
        size_images_spinbox = ttk.Spinbox(
            actions_frame,
            from_=100,
            increment=100,
            to=2000,
            textvariable=size_images,
            width=5,
        )
        size_images_spinbox.grid(row=21, column=0)
        size_images_spinbox.value = size_images  # type: ignore  See tkinter-lifetime above
        ttk.Label(actions_frame, text="Fortschritt:").grid(row=30, column=0)
        progress = tk.DoubleVar(root, value=0)
        progress_bar = ttk.Progressbar(
            actions_frame,
            variable=progress,
            orient=tk.HORIZONTAL,
        )
        progress_bar.value = progress  # type: ignore  See tkinter-lifetime above
        progress_bar.grid(row=31, column=0)
        actions_frame.grid(row=0, column=0, sticky=N)
        # END frame
        self.num_images = num_images
        self.size_images = size_images
        self.progress = progress

        # callback to react on numeric UI input
        self.num_images.trace_add("write", lambda _, __, ___: self.display_current_images())
        self.size_images.trace_add("write", lambda _, __, ___: self.display_current_images())

        self.destination_directories = destination_directories
        self.images = ttk.Frame(mainframe)
        self.images.grid(row=0, column=1)

    def next_image(self) -> None:
        self.images_provider.skim(+1)
        self.display_current_images()

    def previous_image(self) -> None:
        self.images_provider.skim(-1)
        self.display_current_images()

    def display_current_images(self) -> None:
        number_of_images = self.num_images.get()
        images = self.images_provider.get(number_of_images)
        self.display_images(images)
        self.progress.set(self.images_provider.progress())

    def display_images(self, image_files: List[pathlib.Path]) -> None:
        # remove the old ones
        for image in self.images.grid_slaves():
            image.destroy()
        # set the new ones
        size = self.size_images.get()
        for index, image_file in enumerate(image_files):
            image = SelectableImage(self.images, image_file, self.destination_directories, (size, size))
            image.grid(row=0, column=index)


@dataclass
class ProgramOptions:
    source_directory: pathlib.Path
    destination_directory: List[pathlib.Path]


@dataclass
class CommandLineArguments:
    source_directory: Optional[pathlib.Path]
    target_directories: List[pathlib.Path]


def ask_for_directory(description: str, root: tk.Tk) -> Optional[pathlib.Path]:
    possible_directory = tkfd.askdirectory(
        parent=root,
        initialdir=pathlib.Path.home(),
        title=description,
    )
    if len(possible_directory) == 0:
        return None
    else:
        return pathlib.Path(possible_directory)


def insist_for_directory(description: str, explanation: str, root: tk.Tk) -> pathlib.Path:
    directory = None
    while directory is None:
        directory = ask_for_directory(description, root)
        if directory is None:
            tkmb.showwarning(message=explanation)
    return directory


def ask_for_missing_options(arguments: CommandLineArguments, root: tk.Tk) -> ProgramOptions:
    """
    Complete the missing information by askin the user interactively.
    """
    values = copy.deepcopy(arguments)
    if values.source_directory is None:
        values.source_directory = insist_for_directory(
            "Ordner mit allen Bildern auswaehlen.",
            "Quellverzeichnis muss ausgewaehlt sein.",
            root,
        )

    if len(values.target_directories) == 0:
        values.target_directories.append(
            insist_for_directory(
                "Ordner in den die Bilder einsortiert werden sollen auswaehlen.",
                "Mindestens ein Zielverzeichnis muss ausgewaehlt sein.",
                root,
            )
        )
        is_more_to_add = tkmb.askyesno(message="Ein weiteres Zielverzeichnis angeben?")
        while is_more_to_add:
            possible_directory = ask_for_directory(
                "Ordner in den die Bilder einsortiert werden sollen auswaehlen.",
                root,
            )
            if possible_directory is None:
                tkmb.showwarning(message="Kein Verzeichnis gewaehlt!")
            else:
                values.target_directories.append(possible_directory)
            is_more_to_add = tkmb.askyesno(message="Noch ein weiteres Zielverzeichnis angeben?")
    program_options = ProgramOptions(
        values.source_directory,
        values.target_directories,
    )
    return program_options


def parse_arguments(argv=sys.argv[1:]) -> CommandLineArguments:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--quelle",
        type=pathlib.Path,
        dest="source_directory",
        help="Ordner, in dem die zu sortierenden Bilder enthalten sind.",
        default=None,
    )
    parser.add_argument(
        "--ziel",
        type=pathlib.Path,
        dest="target_directories",
        action="append",
        help="Zielordner, in den Bilder kopiert werden koennen."
        "Kann mehrmals angegeben werden, um mehrere Zielordner zu bestimmen.",
    )
    arguments = CommandLineArguments(None, [])
    parser.parse_args(argv, arguments)
    return arguments


def main():
    arguments = parse_arguments()

    root = tk.Tk()
    options = ask_for_missing_options(arguments, root)

    app = PhotoSelectionGUI(
        root,
        options.source_directory,
        options.destination_directory,
    )
    app.display_current_images()

    root.mainloop()


if __name__ == "__main__":
    main()
