.PHONY: all clean

all: build/.lilacyaml-doc

build/.lilacyaml-doc: build/lilac.json build/docs/.timestamp
	bootprint json-schema $< build/docs
	rm build/docs/*.map
	sed -i '/<title>/s/Bootprint/lilac.yaml/' build/docs/index.html
	(cd build/docs && if [[ -n $$(git status -s) ]]; then git add -A && git commit -m 'update docs'; fi)
	touch $@

build/lilac.json: lilac-yaml-schema.yaml build/.timestamp
	./yaml2json < $< > $@

build/.timestamp:
	mkdir build
	touch $@

build/docs/.timestamp: build/.timestamp
	if [[ ! -d build/docs ]]; then git worktree add build/docs gh-pages; fi
	touch $@

clean:
	rm -rf build
