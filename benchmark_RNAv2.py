#!/usr/bin/env python3
import sys
import os
import shlex
import subprocess
from subprocess import Popen, PIPE, STDOUT
import re
import copy
import argparse
import glob


#warnings
def printWarningMsg(msg):
	print("[Warning] " + msg)


# check if file exists and is not empty
def checkIfFile(pathToFile):
	if not(os.path.exists(pathToFile) and os.path.getsize(pathToFile) > 0):
		return False
	return True

# launch subprocess
def subprocessLauncher(cmd, argstdout=None, argstderr=None,	 argstdin=None):
	args = shlex.split(cmd)
	#~ p = subprocess.Popen(args, stdin = argstdin, stdout = argstdout, stderr = argstderr)
	p = subprocess.call(args, stdin = argstdin, stdout = argstdout, stderr = argstderr)
	return p

# find files with a regex
def getFiles(pathToFiles, name): #for instance name can be "*.txt"
	os.chdir(pathToFiles)
	listFiles = []
	for files in glob.glob(name):
		listFiles.append(files)
	return listFiles

# read simulation
def simulateReads(covSR, covLR, skipped, abund, EStype, currentDirectory):
	for sizeSkipped in skipped:
		for relAbund in abund:
			suffix = "_size_" + str(sizeSkipped) + "_abund_" + str(relAbund)
			# simulation
			if EStype == "ES":
				cmdSimul = currentDirectory + "/ES_simulation " + str(sizeSkipped) + " " + str(relAbund) + " " + str(suffix) + " " +  str(covSR) + " " + str(covLR)
			elif EStype == "MES":
				cmdSimul =  currentDirectory + "/MES_simulation " + str(sizeSkipped) + " " + str(relAbund) + " " + str(suffix) +  " " + str(covLR)
			cmdSimul = subprocessLauncher(cmdSimul)

# return number of reads in a fasta
def getFileReadNumber(fileName):
	cmdGrep = """grep ">" -c """ + fileName
	val = subprocess.check_output(['bash','-c', cmdGrep])
	return int(val.decode('ascii'))

# return the sequence of an errorless isoform
def getPerfectSequence(fileName):
	cmdGrep = """grep "[ACGT]" -m 1 """ + fileName
	seq = subprocess.check_output(['bash','-c', cmdGrep])
	return seq.decode('ascii')

	
def getPerfectSequenceLength(fileName):
	cmdWc = """grep "[ACGT]" -m 1 """ + fileName + "| wc"
	seq = subprocess.check_output(['bash','-c', cmdWc])
	return int(seq.decode('ascii').split(" ")[-1].rstrip())


# associate to isoform type the headers of the reference file
def makeReferenceHeadersList(currentDirectory, skipped, abund):
	listFilesPerfect = getFiles(currentDirectory, "perfect*_size_" + skipped + "_abund_" + abund + ".fa")
	print(listFilesPerfect)
	refIsoformTypesToCounts = dict()
	refIsoformTypesToSeq = dict()
	for fileP in listFilesPerfect:
		typeIsoform = fileP.split("_")[2]
		readNb = getFileReadNumber(currentDirectory + "/" + fileP) #get nb of reads
		#~ noIsoform = range(readNb)
		headers = [typeIsoform + str(x) for x in range(readNb)]
		print(headers)
		refIsoformTypesToCounts[typeIsoform] = headers
		perfectSeq = getPerfectSequence(currentDirectory + "/" + fileP)
		refIsoformTypesToSeq[typeIsoform] = perfectSeq.rstrip()
	return (listFilesPerfect, refIsoformTypesToCounts, refIsoformTypesToSeq)

# align triplets of reads
def msa(suffix, msaType,outDir = "/home/marchet/detection-consensus-isoform/results"):
	print("Launch", msaType)
	if msaType == "msa_isoform":
		cmdMSA = "/home/marchet/detection-consensus-isoform/analyze_MSAv2.py -r simulatedLR" + suffix + ".fa -c isoform"
	elif msaType == "msa_exon":
		cmdMSA = "/home/marchet/detection-consensus-isoform/analyze_MSAv2.py -r simulatedLR" + suffix + ".fa "
	elif msaType == "msa_sparc":
		cmdMSA = "/home/marchet/detection-consensus-isoform/analyze_MSAv2.py -r simulatedLR" + suffix + ".fa -s True"
	p = subprocessLauncher(cmdMSA)

# headers of corrected reads file
def getCorrectedHeaders(fileName):
	cmdGrep = """grep ">" """ + fileName
	val = subprocess.check_output(['bash','-c', cmdGrep])
	return val.decode('ascii').split("\n")[:-1] #last item is empty


# get consensus sequence from corrected reads file
def getCorrectedSequence(fileName):
	cmdGrep = """grep ">" -v -m 1 """ + fileName
	val = subprocess.check_output(['bash','-c', cmdGrep])
	return val.decode('ascii').rstrip().upper() #last item is empty


# compare headers coming from an isoform in ref file to headers attributed to an isoform in correction file
def compareRefAndCorrectedHeaders(refIsoformTypesToCounts, correcIsoformTypesToCounts):
	count = dict()
	for typeIsoform in refIsoformTypesToCounts.keys():
		count[typeIsoform] = dict()
		for correcIsoform in correcIsoformTypesToCounts.keys():
			for headersRef in refIsoformTypesToCounts[typeIsoform]:
				for headersCor in correcIsoformTypesToCounts[correcIsoform]:
					if headersRef == headersCor:
						if correcIsoform in count[typeIsoform].keys():
							count[typeIsoform][correcIsoform] += 1
						else:
							count[typeIsoform][correcIsoform] = 1
	return count #for instance {'exclusion': {'exclusion': 5}, 'inclusion': {'inclusion': 5}}
	

# associate to isoform type the headers of the corrected file
def makeCorrectedHeadersList(resultDirectory, currentDirectory, skipped, abund, suffix, refIsoformTypesToCounts):
	listFilesCorrected = getFiles(resultDirectory, "corrected_by_MSA*.fa")
	correcIsoformTypesToCounts = dict()
	correcIsoformTypesToSeq = dict()
	for fileC in listFilesCorrected:
		correctedSequence = getCorrectedSequence(fileC)
		listHeaders = getCorrectedHeaders(fileC)
		listHeaders = [x.split("_")[0][1:] + x.split("_")[1].split(' ')[0] for x in listHeaders] #For instance ['exclusion0', 'exclusion1', 'exclusion2', 'exclusion3', 'exclusion4']
		listIsoforms = [x.split("_")[0][:-1] for x in listHeaders]
		for isoformType in set(listIsoforms): #unique types of isoforms
			correcIsoformTypesToCounts[isoformType] = listHeaders
			correcIsoformTypesToSeq[isoformType] = correctedSequence
	return(correcIsoformTypesToCounts, correcIsoformTypesToSeq)

#compute ratio of isoforms representations in ref and corrected files
def computeRatioIsoforms(refIsoformTypesToCounts, correcIsoformTypesToCounts, currentDirectory, suffix):
	counts = compareRefAndCorrectedHeaders(refIsoformTypesToCounts, correcIsoformTypesToCounts)
	confusionName = currentDirectory + "/matrix_confusion" + suffix + ".txt"
	outConf = open(confusionName, 'w')
	outConf.write("reference correction ratio\n")
	isCorrect = True
	for ref in counts:
		for ref2 in counts:
			if ref2 in counts[ref].keys():
				ratio = counts[ref][ref2] * 1.0 / len(refIsoformTypesToCounts[ref]) if len(refIsoformTypesToCounts[ref]) != 0 else 0
				if ratio != 1:
					isCorrect = False
				outConf.write(ref + " " + ref2 + " " + str(ratio) + "\n")
	outConf.close()
	return confusionName, isCorrect




def alignOnRefMsa(soft, skipped, abund, currentDirectory, resultDirectory):
	suffix = "_size_" + str(skipped) + "_abund_" + str(abund)
	listFileNames = getFiles(resultDirectory, "corrected_by_MSA*.fa")
	for fileC in listFileNames:
		isoform = getCorrectedHeaders(resultDirectory + "/" + fileC)[0].split("_")[0][1:]
		print(isoform, "**********************isoform")
		cmdGrep = "grep "+ isoform + " " + currentDirectory + "/refSequences" + suffix + ".fa -A 1 > " + currentDirectory + "/refSequences" + isoform + suffix + ".fa"
		subprocess.check_output(['bash','-c', cmdGrep])
		cmdGrep = "grep "+ isoform + " " + fileC + " -A 1 > toalign.fa"
		subprocess.check_output(['bash','-c', cmdGrep])
		samFile = open(currentDirectory + "/results" + isoform + soft + suffix + ".sam", 'w')
		cmdAlign = "/home/marchet/bin/Complete-Striped-Smith-Waterman-Library/src/ssw_test " + currentDirectory +"/refSequences" + isoform + suffix + ".fa toalign.fa -c -s"
		p = subprocessLauncher(cmdAlign, samFile)
		samFile.close()
		cmdCp = "cp " + resultDirectory + "/" +  fileC + " " + currentDirectory + "/corrected_reads_by_" + soft + "_" + isoform + suffix + ".fa"
		subprocess.check_output(['bash','-c', cmdCp])



#~ def getExpectedLength(currentDirectory, suffix, isoformType):
	#~ length = getPerfectSequenceLength(currentDirectory + "/perfect_reads_" + isoformType + suffix + ".fa")
	#~ print("222222222222222222222222222222222222222222222222222", length)
	#~ expectedLengths = {}
	#~ refFile = open(currentDirectory + "/refSequences" + suffix + ".fa", 'r')
	#~ lines = refFile.readlines()
	#~ for l in lines:
		#~ if ">" in l:
			#~ targetType = l[1:-1]
		#~ else:
			#~ expectedLengths[targetType] = len(l) - 1
	#~ return expectedLengths


def readSam(soft, suffix, isoformType, currentDirectory):
	blockResults = dict()
	lenResults = dict()
	pathSam = currentDirectory + "/results" +isoformType + soft + suffix + ".sam"
	if os.path.exists(pathSam) and os.path.getsize(pathSam) > 0:
		samFile = open(pathSam, 'r')
		readsSize = []
		lines = samFile.readlines()
		queries = dict()
		for line in lines:
			line = line.rstrip().split('\t')
			query = line[0]
			target = line[2]
			cigar = line[5]
			start = int(line[3]) - 1
			length = len(line[9])
			seq = line[9]
			readsSize.append(length)
			blocks = re.compile("[0-9]+").split(cigar)[1:]
			resultAln = re.compile("[A-Z]|=").split(cigar)[:-1]
			alnLength = 0
			gapsLength = 0
			queries[query] = seq
			if len(blocks) == 1 and len(resultAln) == 1 and blocks[0] == '=': #aligned in one block
				blockResults[query] = {1:target}
				alnLength = int(resultAln[0])
			else:
				if query not in blockResults:
					blockResults[query] = {len(blocks):target}
				else:
					if 1 not in blockResults[query]:
						blockResults[query][len(blocks)] = target
				
				for b,r in zip(blocks, resultAln):
					
					if b != 'D' and b!= 'I':
						alnLength += int(r)
					else:
						gapsLength += int(r)
			if query not in lenResults:
				lenResults[query] = {target:[length, alnLength -start, gapsLength]}
			else:
				lenResults[query][target] = [length, alnLength -start, gapsLength]
		return ( start, readsSize, resultAln, gapsLength, blockResults, alnLength, lenResults, queries)
	else:
		return (None,) * 8



def computeResultsRecallPrecision(corrector, skipped, abund, currentDirectory, soft, refIsoformTypesToSeq, outSize):
	print("********************************************************")
	suffix = "_size_" + str(skipped) + "_abund_" + str(abund)
	
	#~ expectedLengths = getExpectedLength(currentDirectory, suffix, isofType)
	#~ ratioLen = []
	print("%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%", soft)
	for isofType in refIsoformTypesToSeq:
		expectedLengths = getPerfectSequenceLength(currentDirectory + "/perfect_reads_" + isofType + suffix + ".fa")
							

		start, readsSize, resultAln, gapsLength, blockResults, alnLength, lenResults, queries = readSam(soft, suffix, isofType, currentDirectory)
		#~ meanSizes[isofType] = {"realSize" : [], "alignedSize" : []}
		#~ for querySeq, aln in blockResults.items():
			#~ meanSizes[isofType]["realSize"].append(lenResults[querySeq][isofType][0])
			#~ meanSizes[isofType ]["alignedSize"].append(lenResults[querySeq][isofType][1])
		meanReadsSize = round(sum(readsSize)*1.0/len(readsSize),2) if len(readsSize) > 0 else 0
		ratioLen = round(meanReadsSize*100/expectedLengths,2)
		outSize.write(soft + " " + str(ratioLen) + " " +  str(skipped) + " "+ str(abund) +"\n")

		#~ ratioLenE = round(meanExclusionCorrectedSize*100/expectedLengths["exclusion"],2)
		
		print(currentDirectory + "/corrected_reads_by_" + soft + "_" + isofType + suffix + ".fa #####################################################################################")
		cmdHead = "head -2 " + currentDirectory + "/corrected_reads_by_" + soft + "_" + isofType + suffix + ".fa > " + currentDirectory + "/corrected.fa"
		subprocess.check_output(['bash','-c', cmdHead])
		cmdHead = "head -2 " + currentDirectory + "/uncorrected_reads_"  + isofType + suffix + ".fa > " + currentDirectory + "/uncorrected.fa"
		subprocess.check_output(['bash','-c', cmdHead])
		cmdHead = "head -2 " + currentDirectory + "/perfect_reads_" + isofType + suffix + ".fa > " + currentDirectory + "/perfect.fa"
		subprocess.check_output(['bash','-c', cmdHead])
		cmdBench = "python3 " + currentDirectory + "/benchmark-long-read-correction/benchmark.py -c " + currentDirectory + "/corrected.fa -u " + currentDirectory + "/uncorrected.fa -r " + currentDirectory + "/perfect.fa -o " + currentDirectory
		subprocessLauncher(cmdBench)

		cmdSed = "sed -i 's/unknown/" + soft + "/g' " + currentDirectory + "/precision.txt"
		subprocess.check_output(['bash','-c', cmdSed])
		cmdCat = "grep " + soft + " " + currentDirectory + "/precision.txt >> " + currentDirectory + "/precision_tmp.txt"
		subprocess.check_output(['bash','-c', cmdCat])
		
		cmdSed = "sed -i 's/unknown/" + soft + "/g' " + currentDirectory + "/recall.txt"
		subprocess.check_output(['bash','-c', cmdSed])
		cmdCat = "grep " + soft +" "  + currentDirectory +"/recall.txt >> " + currentDirectory + "/recall_tmp.txt"
		subprocess.check_output(['bash','-c', cmdCat])

		cmdSed = "sed -i 's/unknown/" + soft + "/g' " + currentDirectory + "/correct_base_rate.txt"
		subprocess.check_output(['bash','-c', cmdSed])
		cmdCat = "grep " + soft + " " + currentDirectory + "/correct_base_rate.txt >> " + currentDirectory + "/correct_base_rate_tmp.txt"
		subprocess.check_output(['bash','-c', cmdCat])




#\textbf{\huge %(school)s \\}

def writeLatex(options, currentDirectory):
	content = r'''\documentclass{article}
	\usepackage{graphicx}

	\begin{document}
	
	\section{Recall, precision, correct bases rate}
	\begin{figure}[ht!]
	\centering\includegraphics[width=0.8\textwidth]{%(recall)s}
	\caption{\textbf{Recall of correctors on %(coverage)sX reads} Recall values in ordinate are computed after correction for each read experiment, using correctors in absciss.}
	\label{fig:recall}
	\end{figure}
	
	\begin{figure}[ht!]
	\centering\includegraphics[width=0.8\textwidth]{%(precision)s}
	\caption{\textbf{Precision of correctors on %(coverage)sX reads} Precision values in ordinate are computed after correction for each read experiment, using correctors in absciss.}
	\label{fig:precision}
	\end{figure}

	
	\begin{figure}[ht!]
	\centering\includegraphics[width=0.8\textwidth]{%(correctRate)s}
	\caption{\textbf{Correct base rate after correction on %(coverage)sX reads} Correct base rate in ordinate, computed after correction for each read experiment, using correctors in absciss.}
	\label{fig:correctRate}
	\end{figure}

	\section{Reads size}

	\begin{figure}[ht!]
	\centering\includegraphics[width=0.8\textwidth]{%(size)s}
	\caption{\textbf{Ratio of corrected over real isoform length in corrected reads} Coverage of %(coverage)sX, ratio in ordinate, corrector in absciss.}
	\label{fig:size}
	\end{figure}


	\section{Isoform detection}
	\end{document}
	'''
	with open(currentDirectory + '/cover.tex','w') as f:
		f.write(content%options)
	proc = subprocess.Popen(['pdflatex', '-output-directory', currentDirectory, currentDirectory + '/cover.tex'])
	proc.communicate()



#R functions
def printConfusionMatrix(currentDirectory, corrector, confusionFile, suffix):
	Rcmd = "Rscript " + currentDirectory + "/matrice_confusion.R " + confusionFile + " " + corrector  + suffix + " " + currentDirectory
	subprocessLauncher(Rcmd)

def printMetrics(currentDirectory):
	cmdR = "Rscript " + currentDirectory + "/plot_recall.R " + currentDirectory + "/recall.txt " + currentDirectory
	subprocessLauncher(cmdR)
	cmdR = "Rscript " + currentDirectory + "/plot_precision.R " + currentDirectory + "/precision.txt " + currentDirectory
	subprocessLauncher(cmdR)
	cmdR = "Rscript " + currentDirectory + "/plot_correct_base_rate.R " + currentDirectory + "/correct_base_rate.txt " + currentDirectory
	subprocessLauncher(cmdR)
	cmdR = "Rscript " + currentDirectory + "/plot_size.R " + currentDirectory + "/sizes_reads.txt " + currentDirectory
	subprocessLauncher(cmdR)


def computeResultsIsoforms(correc, currentDirectory, skippedExon, abundanceMajor, suffix, refIsoformTypesToCounts, outDir="/home/marchet/detection-consensus-isoform/results"):
	msa(suffix, correc)
	correcIsoformTypesToCounts, correcIsoformTypesToSeq = makeCorrectedHeadersList(outDir, currentDirectory, skippedExon, abundanceMajor, suffix, refIsoformTypesToCounts)
	confusionFile, isCorrect = computeRatioIsoforms(refIsoformTypesToCounts, correcIsoformTypesToCounts, currentDirectory, suffix)
	printConfusionMatrix(currentDirectory, correc, confusionFile, suffix)
	return isCorrect


def main():
	currentDirectory = os.path.dirname(os.path.abspath(sys.argv[0]))
	installDirectory = os.path.dirname(os.path.realpath(__file__))


	outSize = open(currentDirectory + "/sizes_reads.txt", 'w')
	outSize.write("soft size skipped abund\n")
	
	covSR = 1
	#~ skipped = [50,100]
	#~ abund = [50,75,90,10]
	abund = [50]
	skipped = [100]
	skippedS = [str(r) for r in skipped]
	abundS = [str(r) for r in abund]
	EStype = "ES"
	#~ EStype = "MES"

	# Manage command line arguments
	parser = argparse.ArgumentParser(description="Benchmark for quality assessment of long reads correctors.")
	# Define allowed options
	parser = argparse.ArgumentParser()
	parser.add_argument('-output', nargs='?', type=str, action="store", dest="outputDirPath", help="Name for output directory", default=None)
	#~ parser.add_argument('-corrector', type=str, action="store", dest="correctors", help="A particular corrector to be used", default=None)
	parser.add_argument('-coverage', nargs='?', type=int, action="store", dest="covLR", help="Coverage for LR simulation (default 10)", default=20)
	# get options for this run
	args = parser.parse_args()
	outputDirPath = args.outputDirPath
	covLR = args.covLR

	correctors = ["msa_isoform", "msa_exon"]
	#~ correctors = ["msa_isoform"]
	#~ correctors = ["msa_exon"]
	#~ correctors = ["msa_sparc"]
	if not outputDirPath is None:
		if not os.path.exists(outputDirPath):
			os.mkdir(outputDirPath)
		else:
			printWarningMsg(outputDirPath+ " directory already exists, we will use it.")
			try:
				cmdRm = "(cd " + outputDirPath + " && rm *)"
				subprocess.check_output(['bash','-c', cmdRm])
			except subprocess.CalledProcessError:
				pass
				
	simulateReads(covSR, covLR, skipped, abund, EStype, currentDirectory)
	for correc in correctors:
		for skippedExon in skippedS:
			for abundanceMajor in abundS:
				listFilesPerfect, refIsoformTypesToCounts, refIsoformTypesToSeq = makeReferenceHeadersList(currentDirectory, str(skippedExon), str(abundanceMajor))
				suffix = "_size_" + str(skippedExon) + "_abund_" + str(abundanceMajor)
				isCorrect = computeResultsIsoforms(correc, currentDirectory, skippedExon, abundanceMajor, suffix, refIsoformTypesToCounts)
				if isCorrect: # all reads were corrected to the right isoform
					alignOnRefMsa(correc, skippedExon, abundanceMajor, currentDirectory, "/home/marchet/detection-consensus-isoform/results")
					computeResultsRecallPrecision(correc, skippedExon, abundanceMajor, currentDirectory, correc, refIsoformTypesToSeq, outSize)
	cmdMv = "mv " + currentDirectory + "/recall_tmp.txt " + currentDirectory + "/recall.txt"
	subprocess.check_output(['bash','-c', cmdMv])
	cmdMv = "mv " + currentDirectory + "/precision_tmp.txt " + currentDirectory + "/precision.txt"
	subprocess.check_output(['bash','-c', cmdMv])

	cmdMv = "mv " + currentDirectory + "/correct_base_rate_tmp.txt " + currentDirectory + "/correct_base_rate.txt"
	subprocess.check_output(['bash','-c', cmdMv])
	printMetrics(currentDirectory)
	writeLatex({"coverage":str(covLR), "recall": currentDirectory + "/recall.png", "precision": currentDirectory + "/precision.png", "correctRate": currentDirectory + "/correct_base_rate.png", "size":  currentDirectory + "/size.png"}, currentDirectory)

if __name__ == '__main__':
	main()
