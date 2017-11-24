from extractor.candidate import Candidate
from extractor.extractors.abs_extractor import AbsExtractor


class MethodExtractor(AbsExtractor):
    """
    The MethodExtractor tries to extract the methods.
    """

    # weights used in the candidate evaluation:
    # (position, frequency)
    weights = [1.0, 1]

    _copulative_conjunction = ['and', 'as', 'both', 'because', 'even', 'for', 'if ', 'that', 'then', 'since', 'seeing',
                               'so', 'after']

    _stop_words = ['and', 'but', 'lead', 'is', 'has', 'have', 'went', 'was', 'been', 'were', 'get', 'are', 'do', 'so',
                   'due', 'well', 'very', 'on', 'too', 'be', 'i', 'and', 'have', 'the', 'a', ',', '.', '', 'not', "n't",
                   'am', 'as', 'even', 'however', 'other', 'just', 'over', 'more', 'say', 'also']
    _stop_ner = ['TIME', 'DATE', 'ORGANIZATION', 'DURATION', 'ORDINAL']

    # prepositional phrase PP, preposition
    def extract(self, document):
        """
        Parses the document for answers to the questions how.

        :param document: The Document object to parse
        :type document: Document

        :return: The parsed Document object
        """

        self._extract_candidates(document)
        self._evaluate_candidates(document)

        return document

    def _extract_candidates(self, document):

        candidates = []
        postrees = document.get_trees()

        # Preposition or subordinating conjunction -> detecting verbs
        for i, tree in enumerate(postrees):
            for candidate in self._extract_tree_for_prepos_conjunctions(tree):
                candidates.append(candidate)
        candidates = self._filter_duplicates(candidates)

        # candidate detection
        # All kind of adjectives
        candidatesAd = self._filter_duplicates(self._extract_ad_candidates(document))

        # join the candidates
        candidates = candidates + candidatesAd

        # save them to the document
        document.set_candidates('MethodExtractor', candidates)

    def _extract_tree_for_prepos_conjunctions(self, tree):

        # in: before
        # after: after
        candidates = []
        for subtree in tree.subtrees():
            label = subtree.label()

            # Preposition or subordinating conjunction -> detecting verbs
            # ...after it "came off the tracks"...
            if label == 'IN':
                right_sibling = subtree.right_sibling()

                # be sure there is more text on the right side of the tree
                if right_sibling:
                    # check if IN candidate is copulative(also known as addition)

                    # if subtree[0] in self._copulative_conjunction or subtree[0] not in self._prepositions_before:
                    if subtree[0]['nlpToken']['lemma'] in self._copulative_conjunction:
                        # candidate is after the preposition and

                        # if the right sibling (potential candidate) is an location or time
                        # the left sibling is taken as candidate
                        if right_sibling.leaves()[0]['nlpToken']['ner'] not in self._stop_ner:

                            right_sibling_pos = self._pos_linked_to_corenlp_tokens(right_sibling)
                            candidate_parts = self._find_vb_cc_vb_parts(right_sibling_pos)

                            if candidate_parts:
                                # get the CoreNLP tokens for each part e.g lemmas etc.
                                # convert list objects back to tuples for backward compatibility
                                candidates.append(
                                    [candidate_parts, None, tree.stanfordCoreNLPResult['index'], 'prepos'])
                        else:
                            # look at the sentence to the left side
                            # beause of the tree structure simples way is to go multible times up and then walk back
                            atree = subtree.parent().parent().parent()
                            if atree:
                                relevantParts = self._pos_linked_to_corenlp_tokens(atree)
                                candidate_parts = self._find_vb_cc_vb_parts(relevantParts)
                                if candidate_parts:
                                    candidates.append(
                                        [candidate_parts, None, tree.stanfordCoreNLPResult['index'], 'prepos'])

        return candidates

    def _extract_ad_candidates(self, document):
        """
        :param document: The Document to be analyzed.
        :type document: Document

        :return: A List of Tuples containing all agents, actions and their position in the document.
        """

        # retrieve results from preprocessing
        candidates = []

        sentences = document.get_sentences()

        self._maxIndex = 0
        for sentence in sentences:
            for token in sentence['tokens']:
                if token['index'] > self._maxIndex:
                    self._maxIndex = token['index']
                if self._is_relevant_pos(token['pos']) and token['ner'] not in self._stop_ner:
                    candidates.append(
                        [[({'nlpToken': token}, token['pos'], token)], None, sentence['index'], 'adjectiv'])
        return candidates

    def _evaluate_candidates(self, document):
        """
        :param document: The parsed document
        :type document: Document
        :param candidates: Extracted candidates to evaluate.
        :type candidates:[([(String,String)], ([(String,String)])]
        :return: A list of evaluated and ranked candidates
        """
        # ranked_candidates = []
        candidates = document.get_candidates('MethodExtractor')
        lemma_map = document.get_lemma_map()

        # find lemma count per candidate, consider only the the greatest count per candidate
        # (each candidate is/can be a phrase and therefore, has multiple words)
        global_max_lemma = 0
        for candidate in candidates:

            # remove any prev. calculations
            candidate.reset_calculations()

            maxLemma = 0
            for part in candidate.get_parts():
                lemma = part[0]['nlpToken']['lemma']
                lemma_count = 0
                # ignore lemma count for stopwords, because they are very frequent
                if lemma not in self._stop_words:
                    lemma_count = lemma_map[lemma]
                if lemma_count > maxLemma:
                    maxLemma = lemma_count
                if lemma_count > global_max_lemma:
                    global_max_lemma = lemma_count
            # assign the greatest lemma to the candidate
            candidate.set_calculations('lemma_count', maxLemma)

        # normalize frequency (per lemma)
        for candidate in candidates:
            count = candidate.get_calculations('lemma_count')
            candidate.set_calculations('lemma_count_norm', count / global_max_lemma)

        # normalize position - reserved order
        sentences_count = len(document.get_sentences())
        for candidate in candidates:
            freq = (sentences_count - candidate.get_sentence_index()) / sentences_count
            candidate.set_calculations('position_frequency_norm', freq)

        # callculate score
        score_max = 0
        weights_sum = sum(self.weights)
        for candidate in candidates:
            score = ((candidate.get_calculations('lemma_count_norm') * self.weights[1] +
                      candidate.get_calculations('position_frequency_norm') * self.weights[0]
                      ) / weights_sum)
            candidate.set_score(score)
            if score > score_max:
                score_max = score

        # normalize score
        for candidate in candidates:
            score = candidate.get_score()
            candidate.set_score(score / score_max)

        candidates.sort(key=lambda x: x.get_score(), reverse=True)
        document.set_answer('how', self._fix_format(candidates))

    # helper to convert parts to the new format
    def _fix_format(self, candidates):
        result = []
        for candidate in candidates:
            ca = Candidate()
            parts = candidate.get_parts()
            parts_new = []
            for part in parts:
                parts_new.append((part[0], part[1]))
            ca.set_parts(parts_new)
            ca.set_sentence_index(candidate.get_sentence_index())
            ca.set_score(candidate.get_score())
            result.append(ca)
        return result

    def _find_vb_cc_vb_parts(self, relevantParts):
        recording = False
        candidateParts = []
        for relevantPart in relevantParts:
            if relevantPart[1].startswith('VB') or relevantPart[1].startswith('JJ') or relevantPart[1].startswith(
                    'LS') or relevantPart[1] == 'CC':
                candidateParts.append(relevantPart)
                recording = True
            elif recording is True:
                break
        candidatePartsLen = len(candidateParts)

        # filter out short candidates
        if ((candidatePartsLen == 1 and candidateParts[0][0]['nlpToken'][
            'lemma'] not in self._stop_words) or candidatePartsLen > 1):
            return candidateParts
        return None

    def _count_elements(self, root):
        count = 0
        if isinstance(root, list):
            for element in root:
                if isinstance(element, list):
                    count += self._count_elements(element)
                else:
                    count += 1
        else:
            count += 1
        return count

    def _is_relevant_pos(self, pos):
        # Is adjective or adverb
        if pos.startswith('JJ') or pos.startswith('RB'):
            return True
        else:
            return False
