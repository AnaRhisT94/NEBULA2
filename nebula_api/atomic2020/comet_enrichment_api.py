import json
import torch
import re
import spacy
from tqdm import tqdm
from pathlib import Path
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
from nltk.corpus import words
from nebula_api.nebula_enrichment_api import NRE_API
from nebula_api.canonisation_api import CANON_API
# import amrlib
# import penman

from nebula_api.atomic2020.utils import calculate_rouge, use_task_specific_params, calculate_bleu_score, trim_batch


def chunks(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


class Comet:
    def __init__(self, model_path):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = AutoModelForSeq2SeqLM.from_pretrained(model_path).to(self.device)
        self.model.zero_grad()
        self.nre = NRE_API()
        self.canon = CANON_API()
        # self.stog = amrlib.load_stog_model()
        # self.gtos = amrlib.load_gtos_model()
        print("model loaded")
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        task = "summarization"
        use_task_specific_params(self.model, task)
        self.batch_size = 1
        self.decoder_start_token_id = None
        self.triplet_relations = [
            "DefinedAs",
            "HasA",
            "xReason",
            "HasFirstSubevent",
            "HasLastSubevent", 
            "HasSubEvent",
            "HasSubevent",
            "RelatedTo", 
            "isAfter",
            "isBefore",
            "xEffect", 
            "xWant",
            "xIntent",
            "xNeed" 
        ]
        self.person_relations = [
            "xEffect", 
            "xWant",
            "xIntent",
            "xNeed"
            ]
        self.attributes_relations = [ 
            #"InstanceOf",
            #"MadeUpOf",
            "xReact",
            "xAttr"
            ]
        self.comcepts_relations = [ 
            "isFilledBy"
            ]
        self.experts = []

    def generate(
            self, 
            queries,
            decode_method="beam", 
            num_generate=5, 
            ):

        with torch.no_grad():
            examples = queries

            decs = []
            for batch in list(chunks(examples, self.batch_size)):

                batch = self.tokenizer(batch, return_tensors="pt", truncation=True, padding="max_length").to(self.device)
                input_ids, attention_mask = trim_batch(**batch, pad_token_id=self.tokenizer.pad_token_id)
                #print(batch)
                summaries = self.model.generate(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    decoder_start_token_id=self.decoder_start_token_id,
                    num_beams=num_generate *2,
                    num_return_sequences=num_generate,
                    )

                dec = self.tokenizer.batch_decode(summaries, skip_special_tokens=True, clean_up_tokenization_spaces=False)
                decs.append(dec)

            return decs

    def split_event(self, text):
        #import deplacy
        en =spacy.load('en_core_web_sm')
        splits = []
        #text = 'man is holding onto a mackeral and tossing his head back laughing with somebody else'
        doc = en(text)
        #deplacy.render(doc)

        seen = set() # keep track of covered words

        chunks = []
        for sent in doc.sents:
            heads = [cc for cc in sent.root.children if cc.dep_ == 'conj']

            for head in heads:
                words = [ww for ww in head.subtree]
                for word in words:
                    seen.add(word)
                chunk = (' '.join([ww.text for ww in words]))
                chunks.append( (head.i, chunk) )

            unseen = [ww for ww in sent if ww not in seen]
            chunk = ' '.join([ww.text for ww in unseen])
            chunks.append( (sent.root.i, chunk) )

        chunks = sorted(chunks, key=lambda x: x[0])

        for ii, chunk in chunks:
            splits.append(chunk)
        return(splits)

    def add_experts(self, experts):
        self.experts = experts

    def check_triplet(self, triplet):
        triplet = triplet.split(' ')
        if len(triplet) < 4:
            return(False)
        # for concept in triplet:
        #     print(concept)
        #     if concept in words.words() or concept == '':
        #         print("OK")
        #         continue
        #     else:
        #         return(False)
        return(True)
        
    def get_playground_data(self, movie_id, scene_element):
        events = []
        places = []
        lighthouses = self.nre.get_vcomet_data(movie_id)
        for lh in lighthouses:
            if lh['scene_element'] == scene_element:
                print(lh['scene_element'])
                for event in lh['events']:
                    if event[0] >= 0.3:
                        events.append(event[1][0])
                for action in lh['actions']:
                    if action[0] >= 0.35:
                        events.append(action[1][0])
                for place in lh['places']:
                    if place[0] >= 0.3:
                        places.append(place[1])
        return(events, places)

    def get_concepts(self, events, places):
        concepts = self.get_groundings(events, places, type='concepts')
        all_concepts = []
        concepts_map = {}
        for concept in concepts.values():
            for cn in concept:
                #print("Concepts: " + cn)
                for w in cn.split():
                    all_concepts = all_concepts + self.canon.get_concept_from_entity(w)
        all_concepts = list(dict.fromkeys(all_concepts)) 
        for ac in all_concepts:
            #print(ac)
            class_ = self.canon.get_class_of_entity(ac)
            if class_ in concepts_map.keys():
                concepts_map[class_] = concepts_map[class_] + [ac]
            else:
                concepts_map[class_] = [ac]
        return(concepts_map)

    def get_verbs(self, lighthouses):
        relations = self.person_relations
        num_generate = 5
        all_posible_verbs = []
        for lighthouse in lighthouses:
            lighthouse = re.sub("\d+", "PersonX", lighthouse,  count=1)
            lighthouse = re.sub("\d+", "PersonY", lighthouse,  count=1)
            lighthouse = re.sub("\d+", "PersonZ", lighthouse)
            #print(lighthouse)
            for rel in relations:
                queries = []  
                query = "{} {} [GEN]" .format(lighthouse, rel)
                queries.append(query)
                #print(rel)
                results = self.generate(queries, decode_method="beam", num_generate = num_generate)
                for res in results:
                    for r in res:
                        for verb in r.split():
                            relations = self.canon.get_verb_from_concept(verb)
                            for relation in relations:
                                all_posible_verbs.append(relation)
        all_posible_verbs = list(dict.fromkeys(all_posible_verbs))
        return(all_posible_verbs)
            
    def get_groundings(self, events, places=None, type='concepts', person='person'):
        if type == 'concepts':
            relations = self.comcepts_relations
            num_generate = 10
        elif type == 'attributes':
            relations = self.attributes_relations
            num_generate = 10
        elif type == 'triplet':
            relations = self.triplet_relations
            num_generate = 20
        elif type == 'person':
            relations = self.person_relations
            num_generate = 10
        else:
            print("Bad relation type: " + type)
        pplaces = []
        pevents = []
        
        if places:
            for place in places:
                pplaces.append(place)

        for event in events:
            simple_events = self.split_event(event)
            for sevent in simple_events:
                pevents.append(sevent)
        
        lighthouses = pevents + pplaces

        if len(self.experts) == 0:
            personx = ' PersonX'
        else:
            for expert in self.experts:
                personx = personx + " and " + expert
        print(personx)
        groundings_map = {}
        for lighthouse in lighthouses:
            groundings = []
           
            lighthouse, count = re.subn("\d+", personx, lighthouse,  count=1)
            lighthouse = re.sub("\d+", "PersonY", lighthouse,  count=1)
            lighthouse = re.sub("\d+", "PersonZ", lighthouse)
           
            if count < 1:
                lighthouse = " PersonX " + lighthouse
            #print(lighthouse)
            for rel in relations:
                queries = []  
                query = "{} {} [GEN]" .format(lighthouse, rel)
                queries.append(query)
                #print(rel)
                results = self.generate(queries, decode_method="beam", num_generate = num_generate)
                for result in results:
                    for grounding in result:
                        if type == 'triplet':
                            if rel == 'xNeed':
                                grounding = personx + " need" + grounding
                            elif rel == 'xIntent':
                                grounding = personx + " intent" + grounding
                            elif rel == 'xWant':
                                grounding = personx + " want" + grounding
                            
                        #if type == 'triplet':
                            if not self.check_triplet(grounding):
                               continue 
                            grounding = grounding.replace("personx","PersonX")
                            grounding = grounding.replace("Person x","PersonX")
                            grounding = grounding.replace("Person X","PersonX")
                            #grounding = grounding.replace("to","PersonX")
                            grounding = grounding.replace("person x","PersonX")
                            grounding = grounding.replace("they","PersonXY")
                            #print(grounding.split()[0])
                            if len(grounding.split()) > 1:
                                if grounding.split()[0] == "to":
                                    grounding = grounding.replace("to","PersonX", 1)
                                elif grounding.split()[0] != "PersonX":
                                    grounding = " PersonX" + grounding

                        groundings.append(grounding)
                        groundings = list(dict.fromkeys(groundings))
                        #print(grounding)
                groundings_map[lighthouse] = groundings
            #input()
        #groundings = list(dict.fromkeys(groundings))
        return(groundings_map)
        

if __name__ == "__main__":
    print("model loading ...")
    # heads = ["1 hurriedly steps off of the curb into the street carrying her luggage to the car","3 passes by on her way home",
    # "the driver of the car has pulled up next to the woman"]
    # heads = ['2 is holding onto a mackeral and tossing his head back laughing with 1','4 growls at the start of the battle',
    # '2 laughs with the others','1 - 5 stand over a freshly slaughtered hog',
    # '3 places someone ashes in the sea','man stands with one on the beach','on a battlefield over the ocean','on a rocky beach']
    # events = ['4 spots someone up ahead','5 and 7 work at the hotel and are waiting by the doors peering out the glass for someone',
    # '3 eyes someone outside of the office','3 opens the door for the detectives with a calm demeanor','4 looks back as he crosses',
    # '1 quickly escorts someone down the lobby','the group move through the elevator']
    # places = ['in a gatehouse of an airport','at an airport entrance','on the sstreet','outside the staff entrance']
    #movie_id = 'Movies/114206548'
    movie_id = 'Movies/114206999'
    comet = Comet("./comet-atomic_2020_BART")
    #Get data for movie, scene_element
    events, places = comet.get_playground_data(movie_id, 0)
    
    # print("Original lighthouse---------------")
    # print(events)
    # print("Places")
    # print(places)
    # # comet.add_experts(["passport"])
    # res = comet.get_groundings(events, places, 'concepts')
    # print("Concepts.....")
    # print(res)
    # res = comet.get_groundings(events, places, 'attributes')
    # print("Attributes...")
    # print(res)
    # res = comet.get_groundings(events, places, 'person','PersonX')
    # print("Persons, grounded by \"PersonX\"")
    # print(res)
    # res = comet.get_groundings(events, places, 'triplet')
    # print("Triplets")
    # print(res)
    print(comet.get_concepts(events, places))
   
    
      