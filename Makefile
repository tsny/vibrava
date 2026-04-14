.PHONY: zip-res tagger

zip-res:
	zip -r res.zip res/ -x "*Zone.Identifier"

tagger:
	streamlit run tagger/app.py
