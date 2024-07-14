#!/usr/bin/env python3
import sys

def text_to_odt(lines: list, odt_file: str):
    from odf.opendocument import OpenDocumentText
    from odf.text import P
    # Create a new OpenDocument Text document
    doc = OpenDocumentText()

    # Add each line as a paragraph to the document
    for line in lines:
        p = P(text=line)
        doc.text.addElement(p)

    # Save the document
    doc.save(odt_file)

if __name__ == "__main__":
    input_file = sys.argv[1]
    output_file = sys.argv[2]

    with open(input_file, 'r', encoding='utf8') as f:
        lines = f.readlines()
        text_to_odt(lines, output_file)