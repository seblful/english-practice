"""The offline pipeline that turns the printed book into a database.

This is a build tool. It runs on a workstation, once, and everything it
produces is a file:

    cut-pdf                 the book -> the three sections worth reading
    separate-page-images    a section -> one PNG per grammar and exercise page
    ocr-grammar-images      a grammar page -> markdown
    organize-exercises      an exercise page -> one crop per exercise
    extract-answers         a crop + the book's short answer -> full answers
    extract-rules           a crop + the grammar markdown -> the rule behind it
    populate                all of the above -> the SQLite database
    validate                the database -> a report on what is wrong with it
    bundle                  the database -> the copy that ships in the APK

Splitting this out of the bot is what lets the bot's container stop shipping
OpenCV, PyMuPDF and an OCR client to serve a chat that never calls any of them.
Nothing in the running application imports this package, and nothing here
imports the bot or the app.
"""

__version__ = "0.1.0"
