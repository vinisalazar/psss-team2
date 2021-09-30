import argparse
import json
import logging
import sys

import numpy as np
import pandas as pd
import scipy.sparse as sps


def calc_scores(true, pred):
    diff = true - pred
    fp = (diff < 0).sum()
    fn = (diff > 0).sum()
    tp = true.sum() - fn

    metrics = dict()
    metrics['precision'] = tp / (tp + fp)
    metrics['recall'] = tp / (tp + fn)
    return metrics


def qual_metrics(true, pred):
    true_coo = true.tocoo()
    n_bins = 50
    row = true_coo.row
    col = true_coo.col
    pid = true_coo.data
    _, bins = np.histogram(pid, bins=n_bins)
    metrics = ['precision', 'recall']
    pid_metrics = {m: list() for m in metrics}
    pid_metrics['min_qual'] = list()
    for i in range(n_bins):
        s = bins[i]
        pid_mask = pid >= s
        row_mask = row[pid_mask]
        col_mask = col[pid_mask]
        bin_metrics = calc_scores((true[row_mask, col_mask] >= s).astype(int),
                                  (pred[row_mask, col_mask] != 0).astype(int))
        for m in metrics:
            pid_metrics[m].append(bin_metrics[m])
        pid_metrics['min_qual'].append(s)

    return pid_metrics


def main(args):
    """  Example TSV
    qseqid	sseqid	pident	length	mismatch	gapopen	qstart	qend	sstart	send	evalue	bitscore
    nmdc:mga04781_15	nmdc:mga04781_2	97.6	8564	*	*	1	8565	5736	14300	*	*
    nmdc:mga04781_3	nmdc:mga04781_15	95.8	6551	*	*	8865	15416	1	6552	*	*
    """

    # read in files
    true_df = pd.read_csv(args.true_tsv, sep='\t')
    pred_df = pd.read_csv(args.pred_tsv, sep='\t')

    # If predictions have quality scores, we will generate some extra metrics.
    # The third column is assumed to be quality scores.
    pred_has_qual = len(pred_df.columns) > 2

    # map files to indices
    ctgs = set(true_df.iloc[:, 0])
    ctgs.update(true_df.iloc[:, 1])

    # find and filter extra contigs in predictions file
    extras = set(pred_df.iloc[:, 0])
    extras.update(pred_df.iloc[:, 1])
    extras -= ctgs

    if len(extras):
        print((f'Found {len(extras)} extra contigs in {args.pred_tsv}. '
                'Discarding before computing metrics.'), file=sys.stderr)

        mask = np.logical_or(pred_df.iloc[:, 0].isin(ctgs),
                             pred_df.iloc[:, 0].isin(ctgs))
        pred_df = pred_df[mask]

    # build graph
    ## map sequence identifiers to indices
    ctgs = dict(zip(ctgs, range(len(ctgs))))
    true_df['qseqid_idx'] = [ctgs[s] for s in true_df.iloc[:, 0]]
    true_df['sseqid_idx'] = [ctgs[s] for s in true_df.iloc[:, 1]]
    pred_df['qseqid_idx'] = [ctgs[s] for s in pred_df.iloc[:, 0]]
    pred_df['sseqid_idx'] = [ctgs[s] for s in pred_df.iloc[:, 1]]

    ## build adjacency matrix
    n_ctgs = len(ctgs)
    true_g = sps.dok_matrix((n_ctgs, n_ctgs), dtype=float)
    pred_g = sps.dok_matrix((n_ctgs, n_ctgs), dtype=np.int8)
    true_g[true_df['qseqid_idx'], true_df['sseqid_idx']] = true_df.iloc[:, 2]
    pred_g[pred_df['qseqid_idx'], pred_df['sseqid_idx']] = pred_df.iloc[:, 2] if pred_has_qual else 1
    true_g = true_g.tocsr()
    pred_g = pred_g.tocsr()


    # calculate metrics:
    metrics = calc_scores(true_g != 0, pred_g != 0)

    pid_metrics = qual_metrics(true_g, pred_g)
    metrics['recall_qual'] = {'recall': pid_metrics['recall'], 'qual': pid_metrics['min_qual']}

    if pred_has_qual:
        pid_metrics = qual_metrics(pred_g, true_g)
        metrics['precision_qual'] = {'precision': pid_metrics['recall'], 'qual': pid_metrics['min_qual']}

    # output metrics
    if args.output is not None:
        out = open(args.output, 'w')
    else:
        out = sys.stdout

    json.dump(metrics, fp=out)


def parse_argparse_args():
    desc = """
    Assess performance of a contig containment tool
    """
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument("true_tsv", type=str,
                        help="true containments in tabular BLAST output")
    parser.add_argument("pred_tsv", type=str,
                        help="predicted containments in tabular BLAST output")
    parser.add_argument("-o", "--output", type=str,
                        help="the file to save results to", default=None)
    args = parser.parse_args()

    return args


def parse_snakemake_args(snakemake):
    args = argparse.Namespace()
    args.true_tsv = snakemake.input['ground_truth']
    args.pred_tsv = snakemake.input['predicted_containments']
    args.output = snakemake.output['performance_report']
    return args


if 'snakemake' in locals():
    args = parse_snakemake_args(snakemake)
    logging.basicConfig(
    filename=str(snakemake.log),
    encoding="utf-8",
    level=logging.DEBUG,
    format="%(asctime)s %(message)s",
    datefmt="%m/%d/%Y %H:%M:%S",
)
    logging.info(f"Starting script {__file__.split('/')[-1]}.")
    logging.debug(f"Full script path: {__file__}")
    main(args)
    logging.info(f"Done.")
elif __name__ == '__main__':
    args = parse_argparse_args()
    main(args)
