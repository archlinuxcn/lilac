GETTEXT="/usr/lib/python3.7/Tools/i18n/pygettext.py"
MSGFMT=msgfmt

SRCS := $(wildcard *.po)
TARGET = $(patsubst %po, %mo, $(SRCS))

all: $(TARGET)

%.mo: %.po
	$(MSGFMT) -o $@ $<

clean:
	rm -f $(TARGET)
