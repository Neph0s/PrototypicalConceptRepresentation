import os
import argparse
from tqdm import tqdm
import torch
import pdb
import random
import pickle
import numpy as np
import math

def detect_nan_params(model):
		if math.isnan(sum([ i.sum() for i in model.parameters()])):
			return True
		else:
			return False

def clip_grad_norm_(parameters, max_norm, norm_type=2):
	r"""Clips gradient norm of an iterable of parameters.

	The norm is computed over all gradients together, as if they were
	concatenated into a single vector. Gradients are modified in-place.

	Arguments:
		parameters (Iterable[Tensor]): an iterable of Tensors that will have
			gradients normalized
		max_norm (float or int): max norm of the gradients
		norm_type (float or int): type of the used p-norm. Can be ``'inf'`` for
			infinity norm.

	Returns:
		Total norm of the parameters (viewed as a single vector).
	"""
	parameters = list(filter(lambda p: p.grad is not None, parameters))
	max_norm = float(max_norm)
	norm_type = float(norm_type)
	if norm_type == float('inf'):
		total_norm = max(p.grad.data.abs().max() for p in parameters)
	else:
		total_norm = 0
		for p in parameters:
			param_norm = p.grad.data.norm(norm_type)
			total_norm += param_norm ** norm_type
		total_norm = total_norm ** (1. / norm_type)
		#grads = sum([ p.grad.norm() for p in parameters])

	clip_coef = max_norm / (total_norm + 1e-6)

	if clip_coef < 1:
		#print('clip_coef < 1', clip_coef)
		#print('Before , my sum ',sum([ p.grad.norm() for p in parameters]))
		#pdb.set_trace()
		for p in parameters:
			#print('before ', p.grad.norm() )
			p.grad.data.mul_(clip_coef)
			#print('after  ', p.grad.norm() )

		total_norm = 0
		for p in parameters:
			param_norm = p.grad.data.norm(norm_type)
			total_norm += param_norm ** norm_type
		total_norm = total_norm ** (1. / norm_type)
		print('After ',sum([ p.grad.norm() for p in parameters]), total_norm)
	else:
		print('No clip ', total_norm)
		#print('clip_coef ', clip_coef)
	return total_norm


def ratio_split(isSubclassOf_triples):
	dataset_size = len(isSubclassOf_triples)
	split_idx = int(0.7 * dataset_size)

	train_triples = isSubclassOf_triples[:split_idx]
	test_triples = isSubclassOf_triples[split_idx:]

	return train_triples, test_triples

def cover_split(isSubclassOf_triples, concepts, num_train_triples=-1):
	dataset_size = len(isSubclassOf_triples)
	
	if num_train_triples == -1:
		num_train_triples = int(0.7 * dataset_size)

	train_triples = []
	test_triples = []
	remaining_concepts = set(concepts)
	ent_ratio = 0.4

	total_ents_of_concepts = { con: 0 for con in concepts }

	for triple in isSubclassOf_triples:
		con1 = triple[0]
		con2 = triple[1]
		total_ents_of_concepts[con1] += 1
		total_ents_of_concepts[con2] += 1

	count_ents_of_concepts = { con: 0 for con in concepts }

	
	for triple in isSubclassOf_triples:
		con1 = triple[0]
		con2 = triple[1]
		if con1 in remaining_concepts or con2 in remaining_concepts:
			train_triples.append(triple)
			count_ents_of_concepts[con1] += 1
			count_ents_of_concepts[con2] += 1

			if count_ents_of_concepts[con1] >= math.ceil(ent_ratio * total_ents_of_concepts[con1]):
				remaining_concepts.discard(con1)
			if count_ents_of_concepts[con2] >= math.ceil(ent_ratio * total_ents_of_concepts[con2]):
				remaining_concepts.discard(con2)
		else:
			test_triples.append(triple)

	#pdb.set_trace()
	num_diff = max(num_train_triples - len(train_triples), 0)
	#pdb.set_trace()
	random.shuffle(test_triples)
	train_triples = train_triples + test_triples[:num_diff]
	test_triples = test_triples[num_diff:]
	
	num_test_triples = int(len(test_triples)/2)
	valid_triples = test_triples[:num_test_triples]
	test_triples = test_triples[num_test_triples:]

	print('Num Train Triples {0} Valid Triples {1} Test Triples {2}'.format(len(train_triples), len(valid_triples), len(test_triples)))
	return train_triples, valid_triples, test_triples

