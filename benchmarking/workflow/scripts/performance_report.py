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

def build_graphs(true, pred):
    pass

def main(args):
    """  Example TSV
    qseqid	sseqid	pident	length	mismatch	gapopen	qstart	qend	sstart	send	evalue	bitscore
    nmdc:mga04781_15	nmdc:mga04781_2	97.6	8564	*	*	1	8565	5736	14300	*	*
    nmdc:mga04781_3	nmdc:mga04781_15	95.8	6551	*	*	8865	15416	1	6552	*	*
    """

    # read in files
    true_df = pd.read_csv(args.true_tsv, sep='\t')
    pred_df = pd.read_csv(args.pred_tsv, sep='\t')

    # map files to indices
    ctgs = set(true_df['qseqid'])
    ctgs.update(true_df['sseqid'])

    # find and filter extra contigs in predictions file
    extras = set(pred_df['qseqid'])
    extras.update(pred_df['sseqid'])
    extras -= ctgs

    if len(extras):
        print((f'Found {len(extras)} extra contigs in {args.pred_tsv}. '
                'Discarding before computing metrics.'), file=sys.stderr)

        mask = np.logical_or(pred_df['qseqid'].isin(ctgs),
                             pred_df['sseqid'].isin(ctgs))
        pred_df = pred_df[mask]

    # build graph
    ## map sequence identifiers to indices
    ctgs = dict(zip(ctgs, range(len(ctgs))))
    true_df['qseqid_idx'] = [ctgs[s] for s in true_df['qseqid']]
    true_df['sseqid_idx'] = [ctgs[s] for s in true_df['sseqid']]
    pred_df['qseqid_idx'] = [ctgs[s] for s in pred_df['qseqid']]
    pred_df['sseqid_idx'] = [ctgs[s] for s in pred_df['sseqid']]

    ## build adjacency matrix
    n_ctgs = len(ctgs)
    true_g = sps.dok_matrix((n_ctgs, n_ctgs), dtype=float)
    pred_g = sps.dok_matrix((n_ctgs, n_ctgs), dtype=np.int8)
    true_g[true_df['qseqid_idx'], true_df['sseqid_idx']] = true_df['pident']
    pred_g[pred_df['qseqid_idx'], pred_df['sseqid_idx']] = 1
    true_coo = true_g.tocoo()              # hold onto this for extract pident bins
    true_g = true_g.tocsr()
    pred_g = pred_g.tocsr()


    # calculate metrics:
    metrics = calc_scores(true_g != 0, pred_g)

    # calculate metrics across PID
    n_bins = 50
    row = true_coo.row
    col = true_coo.col
    pid = true_coo.data
    _, bins = np.histogram(pid, bins=n_bins)
    pid_metrics = {m: list() for m in metrics}
    pid_metrics['min_pid'] = list()
    for i in range(n_bins):
        s = bins[i]
        pid_mask = pid >= s
        row_mask = row[pid_mask]
        col_mask = col[pid_mask]

        bin_metrics = calc_scores(true_g[row_mask, col_mask] >= s,
                                  pred_g[row_mask, col_mask])
        for m in metrics:
            pid_metrics[m].append(bin_metrics[m])
        pid_metrics['min_pid'].append(s)

    del pid_metrics['precision']
    metrics['pid_metrics'] = pid_metrics

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